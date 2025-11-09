#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vue_i18n_wrap_v2.py — Backward-compatible i18n preprocessor for Vue + JS/TS and optional Python (.py) Doctype files.

Key points
- Preserves current behaviour for .vue/.js/.ts identically.
- Adds **opt-in** Python support via `--enable-python` to wrap static labels in server-side
  Doctype-like dicts: {"label": "Subject", ...} -> {"label": _("Subject"), ...}
- Safe guards against already wrapped strings, interpolations, and complex literals.
- Supports atomic writes, unified-diff dry-run, JSON report, ignore globs, and threads.
- Technical terms exclusion: Prevents wrapping system-specific terms (desk, helpdesk, frappe, etc.)

IMPORTANT SAFETY WARNINGS
--------------------------
1. **JSON FILES ARE NEVER PROCESSED**: DocType JSON files contain database values (options, defaults,
   fieldnames) that MUST NOT be translated. Wrapping these breaks validation and database operations.
   
2. **UNSAFE KEYS ARE FILTERED**: The following keys are never wrapped even in Python files:
   - 'options' (Select field values - these are DB values!)
   - 'default' (default field values)
   - 'fieldname', 'fieldtype', 'name', 'doctype', 'module', 'app_name'
   
3. **DATABASE VALUES ARE DETECTED**: Common status values like "Published", "Draft", "Active" etc.
   are automatically skipped to prevent database value translation.
   
4. **ALWAYS DRY-RUN FIRST**: Use --dry-run --diff to preview changes before applying.

Usage Examples
--------------

1. Check for missing translations (scan only, no writes):
   python3 vue_i18n_wrap.py \\
     --target /path/to/helpdesk/desk/src \\
     --check-missing-po \\
     --po-file /path/to/helpdesk/helpdesk/locale/tr.po

2. Auto-append missing translations as skeleton entries:
   python3 vue_i18n_wrap.py \\
     --target /path/to/helpdesk/desk/src \\
     --check-missing-po \\
     --po-file /path/to/helpdesk/helpdesk/locale/tr.po \\
     --write-missing-po

3. Wrap Vue/JS/TS files (dry-run to preview changes):
   python3 vue_i18n_wrap.py \\
     --target /path/to/helpdesk/desk/src \\
     --dry-run \\
     --diff

4. Apply wrapping to Vue/JS/TS files (writes files, creates .bak backups):
   python3 vue_i18n_wrap.py \\
     --target /path/to/helpdesk/desk/src

5. Include Python files with custom keys (USE WITH CAUTION):
   python3 vue_i18n_wrap.py \\
     --target /path/to/helpdesk/helpdesk \\
     --enable-python \\
     --py-keys "label,description" \\
     --dry-run --diff  # Always preview first!

6. Wrap Button/tag content with custom tags:
   python3 vue_i18n_wrap.py \\
     --target /path/to/helpdesk/desk/src \\
     --wrap-tag-content "Button,CustomButton" \\
     --wrap-toast

Technical Terms
---------------
The following terms are excluded from wrapping (see TECHNICAL_TERMS set):
- Frappe ecosystem: desk, helpdesk, insights, frappe, erpnext, hrms, crm
- Protocols: smtp, imap, oauth, saml, ldap
- Formats: api, json, xml, csv, pdf

This file is a whole, production-grade drop-in; do not patch piecemeal.
"""

from __future__ import annotations
import argparse
import concurrent.futures as cf
import dataclasses
import difflib
import fnmatch
import hashlib
import io
import json
import os
import pathlib
import re
import shutil
import sys
import tempfile
import logging
import datetime
from typing import Iterable, List, Optional, Pattern, Tuple

# ── Shared ─────────────────────────────────────────────────────────────────────
ALREADY_WRAPPED_JS = re.compile(r"__\s*\(", re.S)
ALREADY_WRAPPED_PY = re.compile(r"(?:\b_|frappe\._)\s*\(", re.S)

NEWLINE = "\n"

# Simple module logger — writes to stderr by default. Callers may configure logging further.
logger = logging.getLogger(__name__)
if not logger.handlers:
	h = logging.StreamHandler()
	h.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
	logger.addHandler(h)
	logger.setLevel(logging.WARNING)

# ── Technical terms exclusion list ────────────────────────────────────────────
# Frappe/ERPNext/Helpdesk specific technical terms that should not be translated
TECHNICAL_TERMS = {
	"desk",       # Frappe Desk UI
	"helpdesk",   # App name
	"insights",   # App name
	"frappe",     # Framework name
	"erpnext",    # Product name
	"hrms",       # Product name
	"crm",        # Common acronym
	"api",        # Technical term
	"json",       # Technical format
	"xml",        # Technical format
	"csv",        # Technical format
	"pdf",        # Technical format
	"smtp",       # Protocol
	"imap",       # Protocol
	"oauth",      # Protocol
	"saml",       # Protocol
	"ldap",       # Protocol
}


def _is_technical_term(text: str) -> bool:
	"""Check if the text is a technical term that should not be translated.
	
	Returns True if the text (case-insensitive) matches a known technical term.
	"""
	return text.strip().lower() in TECHNICAL_TERMS


DATABASE_VALUE_BLACKLIST = {
	"draft",
	"published",
	"archived",
	"active",
	"inactive",
	"open",
	"closed",
	"pending",
	"completed",
	"cancelled",
	"yes",
	"no",
	"true",
	"false",
	"none",
	"null",
	"high",
	"medium",
	"low",
	"urgent",
}


def _is_literal_database_value(text: str) -> bool:
	"""Detect strings that look like database/state values and should not be translated."""
	trimmed = text.strip()
	if not trimmed:
		return True
	lower = trimmed.lower()
	if lower in DATABASE_VALUE_BLACKLIST:
		return True
	if trimmed.isdigit():
		return True
	if len(trimmed) < 3:
		return True
	if ' ' not in trimmed and trimmed.islower():
		return True
	return False

# ── TEMPLATE side (Vue) ───────────────────────────────────────────────────────
TEMPLATE_BLOCK_RE = re.compile(r"(<template[^>]*>)(.*?)(</template>)", re.S | re.I)

PLAIN_ATTR_RE     = r'(?<![\w:-])({attr})\s*=\s*"([^"\n\r]+)"'
PLAIN_ATTR_RE_SQ  = r"(?<![\w:-])({attr})\s*=\s*'([^'\n\r]+)'"
BOUND_ATTR_STR_RE    = r':({attr})\s*=\s*\"\'\s*([^\"\'\n\r]+?)\s*\'\"'
BOUND_ATTR_STR_RE_SQ = r":({attr})\s*=\s*'\"\s*([^\"'\n\r]+?)\s*\"'"
BOUND_ATTR_TPL_RE = r":({attr})\s*=\s*`([^`]+?)`"


def _wrap_template_attr(m: re.Match) -> str:
	attr, text = m.group(1), m.group(2)
	if ALREADY_WRAPPED_JS.search(text):
		return m.group(0)
	if re.search(r"{{|}}|`", text):  # interpolation / template literal
		return m.group(0)
	# Skip technical terms (Frappe/app names, protocols, etc.)
	if _is_technical_term(text):
		return m.group(0)
	# Preserve original attribute quoting when possible. We inspect the raw
	# matched string to see whether the original used single or double quotes
	# and choose an inner JS literal that avoids matching that outer quote.
	orig = m.group(0)
	outer_quote = '"' if '=%s' % '"' in orig or f'{attr}="' in orig else "'"

	def _js_literal_with_outer(s: str, outer: str) -> str:
		# escape backslashes first
		s2 = s.replace("\\", "\\\\")
		# Prefer a quote that is different from outer to avoid needing escapes
		if outer == '"':
			# favor single-quoted inner literal
			if "'" not in s2:
				return "'" + s2 + "'"
			if '"' not in s2:
				return '"' + s2.replace('"', '\\"') + '"'
			# both present: fall back to single with escaped single quotes
			return "'" + s2.replace("'", "\\'") + "'"
		else:
			# outer is single quote, favor double-quoted inner literal
			if '"' not in s2:
				return '"' + s2 + '"'
			if "'" not in s2:
				return "'" + s2.replace("'", "\\'") + "'"
			return '"' + s2.replace('"', '\\"') + '"'

	js_lit = _js_literal_with_outer(text, outer_quote)
	# Always produce a v-bind (:) attribute; preserve outer quoting style
	if outer_quote == '"':
		return f":{attr}=\"__({js_lit})\""
	else:
		return f":{attr}='__({js_lit})'"


def _wrap_attrs_in_text(block: str, attrs: Iterable[str]) -> str:
	s = block
	for attr in attrs:
		a = re.escape(attr)
		s = re.sub(PLAIN_ATTR_RE.format(attr=a), _wrap_template_attr, s)
		s = re.sub(PLAIN_ATTR_RE_SQ.format(attr=a), _wrap_template_attr, s)
		s = re.sub(BOUND_ATTR_STR_RE.format(attr=a), _wrap_template_attr, s)
		s = re.sub(BOUND_ATTR_STR_RE_SQ.format(attr=a), _wrap_template_attr, s)
		s = re.sub(BOUND_ATTR_TPL_RE.format(attr=a), _wrap_template_attr, s)
	return s


VUE_TRANSLATION_MODULE_PATTERN = r'["\']@/translation(?:/[^"\']*)?["\']'
TS_TRANSLATION_MODULE_PATTERN = r'["\'][^"\']*translation(?:/[^"\']*)?["\']'


def _translation_import_patterns(module_pattern: str) -> List[Pattern]:
	templates = [
		r'import\s+\{[^}]*\b__\b[^}]*\}\s+from\s+' + module_pattern,
		r'import\s+__\s+from\s+' + module_pattern,
		r'from\s+' + module_pattern + r'\s+import\s+\{[^}]*\b__\b[^}]*\}',
	]
	return [re.compile(pattern, re.M) for pattern in templates]


def _has_translation_import(text: str, module_pattern: str) -> bool:
	return any(pattern.search(text) for pattern in _translation_import_patterns(module_pattern))


def process_template(html: str, attrs: Iterable[str]) -> str:
	def repl(m: re.Match) -> str:
		start, inner, end = m.group(1), m.group(2), m.group(3)
		return f"{start}{_wrap_attrs_in_text(inner, attrs)}{end}"

	return TEMPLATE_BLOCK_RE.sub(repl, html)


# ── Global tag pass (covers outside <template> too) ────────────────────────────
TAG_RE = re.compile(r"(<(?!/|!)[^>\s][^>]*>)", re.S)  # excludes closing and comments/doctype


def process_all_tags(text: str, attrs: Iterable[str]) -> str:
	def repl(m: re.Match) -> str:
		tag = m.group(1)
		new_tag = _wrap_attrs_in_text(tag, attrs)
		return new_tag

	return TAG_RE.sub(repl, text)


# ── SCRIPT side (<script> in .vue + standalone .ts/.js) ───────────────────────
SCRIPT_BLOCK_RE = re.compile(r"(<script[\s\S]*?>)([\s\S]*?)(</script>)", re.I)

JS_PROP_SQ_TMPL = r"(\b{key}\b)\s*:\s*'([^'\\\n\r]+)'"
JS_PROP_DQ_TMPL = r'(\b{key}\b)\s*:\s*"([^"\\\n\r]+)"'


def _wrap_js_prop(m: re.Match) -> str:
	key, text = m.group(1), m.group(2)
	if ALREADY_WRAPPED_JS.search(text):
		return m.group(0)
	if re.search(r"[`]|{{|}}", text):
		return m.group(0)
	# Skip technical terms (Frappe/app names, protocols, etc.)
	if _is_technical_term(text):
		return m.group(0)
	if _is_literal_database_value(text):
		return m.group(0)
	# Use same quoting strategy as template side for JS literals
	def _js_literal(s: str) -> str:
		s2 = s.replace("\\", "\\\\")
		if "'" not in s2:
			return "'" + s2 + "'"
		if '"' not in s2:
			return '"' + s2.replace('"', '\\"') + '"'
		return "'" + s2.replace("'", "\\'") + "'"

	js_lit = _js_literal(text)
	return f"{key}: __({js_lit})"


def process_js_code(js_text: str, keys: Iterable[str]) -> str:
	s = js_text
	for k in keys:
		kk = re.escape(k)
		s = re.sub(JS_PROP_SQ_TMPL.format(key=kk), _wrap_js_prop, s)
		s = re.sub(JS_PROP_DQ_TMPL.format(key=kk), _wrap_js_prop, s)
	return s


def _inject_vue_import(text: str) -> str:
	"""Inject `import { __ } from "@/translation";` if __ is used but import is missing.
	
	Inserts after existing imports in <script> block, or at the start of script if no imports exist.
	
	Safety measures:
	- Only inject if __ is actually used
	- Skip if import already exists (checks multiple patterns)
	- Never inject inside `import {` blocks
	- Insert after last complete import statement
	"""
	# Check if __ is used anywhere in the file
	if not ALREADY_WRAPPED_JS.search(text):
		return text
	
	# Skip if import already exists
	if _has_translation_import(text, VUE_TRANSLATION_MODULE_PATTERN):
		return text

	def inject_in_script(m: re.Match) -> str:
		start, inner, end = m.group(1), m.group(2), m.group(3)
		
		# Double-check import doesn't exist in this script block
		if _has_translation_import(inner, VUE_TRANSLATION_MODULE_PATTERN):
			return m.group(0)
		
		lines = inner.split('\n')
		insert_idx = 0
		
		# Find last COMPLETE import statement (not inside import { })
		last_import_idx = -1
		in_multiline_import = False
		
		for i, line in enumerate(lines):
			stripped = line.strip()
			
			# Track multiline imports
			if 'import' in stripped and '{' in stripped and '}' not in stripped:
				in_multiline_import = True
			elif in_multiline_import and '}' in stripped:
				in_multiline_import = False
				last_import_idx = i  # This is the end of multiline import
			elif not in_multiline_import and stripped.startswith('import '):
				# Single-line import
				last_import_idx = i
		
		if last_import_idx >= 0:
			# Insert after last import (add 1 to go to next line)
			insert_idx = last_import_idx + 1
			
			# If next line is empty, use it; otherwise insert before next code
			if insert_idx < len(lines) and not lines[insert_idx].strip():
				# Replace empty line with import
				lines[insert_idx] = 'import { __ } from "@/translation";'
			else:
				# Insert new line
				lines.insert(insert_idx, 'import { __ } from "@/translation";')
		else:
			# No imports found, insert at start (after initial empty lines/comments)
			for i, line in enumerate(lines):
				stripped = line.strip()
				if stripped and not stripped.startswith('//') and not stripped.startswith('/*'):
					insert_idx = i
					break
			lines.insert(insert_idx, 'import { __ } from "@/translation";')
		
		new_inner = '\n'.join(lines)
		return f"{start}{new_inner}{end}"
	
	return SCRIPT_BLOCK_RE.sub(inject_in_script, text)


def _inject_ts_import(text: str) -> str:
	"""Inject `import { __ } from "@/translation";` in standalone TS/JS files if __ is used.
	
	This is for .ts/.js files (not .vue files, which are handled by _inject_vue_import).
	
	Safety measures:
	- Only inject if __ is actually used
	- Skip if import already exists
	- Skip files that only contain exports/types/re-exports (no executable code)
	- Check for existing import from './translation' or other paths
	- Insert after last import statement
	"""
	# Check if __ is used anywhere in the file
	if not ALREADY_WRAPPED_JS.search(text):
		return text
	
	# Check if import already exists
	if _has_translation_import(text, TS_TRANSLATION_MODULE_PATTERN):
		return text

	# Check if this file only contains pure exports/types/declarations
	# (no actual executable code that would use __)
	lines = text.split('\n')
	has_executable_code = False
	
	for line in lines:
		stripped = line.strip()
		# Skip empty lines and comments
		if not stripped or stripped.startswith('//') or stripped.startswith('/*') or stripped.startswith('*'):
			continue
		# Skip pure export/type/interface/declare lines
		if (stripped.startswith('export {') or 
		    stripped.startswith('export type ') or
		    stripped.startswith('export interface ') or
		    stripped.startswith('interface ') or
		    stripped.startswith('type ') or
		    stripped.startswith('declare ') or
		    stripped.startswith('import type ') or
		    stripped.startswith('import {')):
			continue
		# If we find any other code, consider it executable
		has_executable_code = True
		break
	
	# Don't inject import in pure type/export files
	if not has_executable_code:
		return text
	
	# Find last import statement
	last_import_idx = -1
	in_multiline_import = False
	
	for i, line in enumerate(lines):
		stripped = line.strip()
		
		# Track multiline imports
		if 'import' in stripped and '{' in stripped and '}' not in stripped:
			in_multiline_import = True
		elif in_multiline_import and '}' in stripped:
			in_multiline_import = False
			last_import_idx = i
		elif not in_multiline_import and stripped.startswith('import '):
			last_import_idx = i
	
	# Insert after last import
	if last_import_idx >= 0:
		insert_idx = last_import_idx + 1
		
		# If next line is empty, use it; otherwise insert new line
		if insert_idx < len(lines) and not lines[insert_idx].strip():
			lines[insert_idx] = 'import { __ } from "@/translation";'
		else:
			lines.insert(insert_idx, 'import { __ } from "@/translation";')
	else:
		# No imports found, insert at start (after initial comments/empty lines)
		insert_idx = 0
		for i, line in enumerate(lines):
			stripped = line.strip()
			if stripped and not stripped.startswith('//') and not stripped.startswith('/*'):
				insert_idx = i
				break
		lines.insert(insert_idx, 'import { __ } from "@/translation";')
	
	return '\n'.join(lines)


def process_vue_file(
	text: str,
	attr_keys: Iterable[str],
	js_keys: Iterable[str],
	wrap_tags: Optional[Iterable[str]] = None,
	wrap_toast: bool = False
) -> str:
	out = process_template(text, attr_keys)

	def s_repl(m: re.Match) -> str:
		start, inner, end = m.group(1), m.group(2), m.group(3)
		return f"{start}{process_js_code(inner, js_keys)}{end}"

	out = SCRIPT_BLOCK_RE.sub(s_repl, out)
	out = process_all_tags(out, attr_keys)
	
	# Optional: wrap tag content (e.g., Button inner text)
	if wrap_tags:
		out = wrap_tag_content(out, wrap_tags)
	
	# Optional: wrap toast messages
	if wrap_toast:
		out = wrap_toast_messages(out)
	
	out = fix_v_model_accidents(out)
	
	# Auto-inject import if __ is used
	out = _inject_vue_import(out)
	
	return out


# ── Python (.py) Doctype-side support (opt-in) ────────────────────────────────
# We only touch simple literal string values of specific keys (default: 'label').
# Example: {"label": "Subject"} -> {"label": _("Subject")}
# We avoid touching complex expressions, f-strings, format strings, and already wrapped values.
# IMPORTANT: We DO NOT wrap JSON files (DocType definitions) to avoid breaking Select field options
# and other database-stored values that must remain in their original form.

# "label": 'Text' OR 'label': "Text"
PY_PROP_SQ_TMPL = r"([\"']{key}[\"'])\s*:\s*'([^'\\\n\r]+)'"
PY_PROP_DQ_TMPL = r"([\"']{key}[\"'])\s*:\s*\"([^\"\\\n\r]+)\""

# Fields that should NEVER be wrapped (database values, options, etc.)
UNSAFE_KEYS = {
	"options",      # Select field options - these are DB values!
	"default",      # Default values for fields
	"fieldname",    # Field names
	"fieldtype",    # Field types
	"name",         # DocType names
	"doctype",      # DocType references
	"module",       # Module names
	"app_name",     # App identifiers
	"status",       # Status values (when used as values, not labels)
}



@dataclasses.dataclass
class PyWrapConfig:
	func: str = "_"  # i18n function name
	qualify: Optional[str] = "frappe._"  # also accept qualified existing calls
	keys: Tuple[str, ...] = ("label",)
	inject_import: bool = True


def _already_wrapped_py(text: str, cfg: PyWrapConfig) -> bool:
	if cfg.func != "_":
		pattern = re.compile(rf"\b{re.escape(cfg.func)}\s*\(")
		return bool(pattern.search(text))
	return bool(ALREADY_WRAPPED_PY.search(text))


def _py_string_is_simple(text: str) -> bool:
	# Conservative skip for f-strings/format placeholders/brace-rich strings.
	if any(sym in text for sym in ("{", "}", "%(", "\n", "\r")):
		return False
	return True


def _wrap_py_prop_factory(cfg: PyWrapConfig):
	def _wrap(m: re.Match) -> str:
		key_tok, val = m.group(1), m.group(2)
		if _already_wrapped_py(val, cfg):
			return m.group(0)
		if not _py_string_is_simple(val):
			return m.group(0)
		
		# Skip literals that look like database values or identifiers
		if _is_literal_database_value(val):
			return m.group(0)
		
		safe = val.replace("\\", "\\\\").replace("\"", "\\\"").replace("'", "\\'")
		# Preserve original quote style by not reusing it (wrap with cfg.func call)
		return f"{key_tok}: {cfg.func}(\"{safe}\")"

	return _wrap


def process_python_code(py_text: str, cfg: PyWrapConfig) -> str:
	"""Process Python code to wrap translatable strings.
	
	IMPORTANT: This function filters out unsafe keys that should never be wrapped,
	such as 'options' (Select field values), 'default', 'fieldname', etc.
	"""
	s = py_text
	
	# Filter out unsafe keys from the config
	safe_keys = [k for k in cfg.keys if k not in UNSAFE_KEYS]
	
	if not safe_keys:
		# If all keys are unsafe, don't process anything
		return s
	
	for k in safe_keys:
		kk = re.escape(k)
		s = re.sub(PY_PROP_SQ_TMPL.format(key=kk), _wrap_py_prop_factory(cfg), s)
		s = re.sub(PY_PROP_DQ_TMPL.format(key=kk), _wrap_py_prop_factory(cfg), s)
	# Optionally inject `from frappe import _` if we created at least one call and it's missing.
	if cfg.inject_import and cfg.func == "_":
		if "_\(" in s and not re.search(r"^\s*from\s+frappe\s+import\s+_\s*$", s, re.M):
			s = _inject_import(s, line="from frappe import _")
	return s


def _normalize_wrapped(text: str) -> str:
	"""Fix legacy wrapped calls that contain escaped quotes like __(\'Close\') -> __('Close')

	This normalizer fixes common artifacts introduced by older versions of the tool
	that injected backslashes before quotes inside the i18n call. It is conservative
	and only unescapes the surrounding quotes of the immediate argument.
	"""
	# __('\'Text\') -> __('Text') and __("\"Text\") -> __("Text")
	text = re.sub(r"__\(\s*\\'([^\\']*?)\\'\s*\)", r"__('\1')", text)
	text = re.sub(r'__\(\s*\\\"([^\\\"]*?)\\\"\s*\)', r'__("\1")', text)

	# More general case: if surrounding quotes are escaped with a single backslash
	# (e.g. __(\'Text\') or __(\"Text\") ) unify to simple quoted arg
	text = re.sub(r"__\(\s*\\(['\"])" r"(.*?)" r"\\\1\s*\)", r"__(\1\2\1)", text)

	# Also handle double-escaped sequences (some files may contain `\\'`)
	text = re.sub(r"__\(\s*\\\\(['\"])" r"(.*?)" r"\\\\\1\s*\)", r"__(\1\2\1)", text)

	return text


def _inject_import(text: str, line: str) -> str:
	# Insert after shebang/encoding/comments at the top, before first non-comment code.
	lines = text.splitlines()
	insert_at = 0
	# Shebang
	if lines and lines[0].startswith("#!"):
		insert_at = 1
	# Encoding cookie
	if insert_at < len(lines) and re.match(r"^#.*coding[:=]", lines[insert_at] or ""):
		insert_at += 1
	# Skip initial block of comments/empty lines
	while insert_at < len(lines) and (not lines[insert_at].strip() or lines[insert_at].lstrip().startswith("#")):
		insert_at += 1
	lines.insert(insert_at, line)
	return NEWLINE.join(lines) + (NEWLINE if text.endswith(("\n", "\r")) else "")


# ── v-model accident fixer ────────────────────────────────────────────────────

def fix_v_model_accidents(text: str) -> str:
	# v-model::title="__('x.y')" -> v-model:title="x.y"
	text = re.sub(
		r"v-model::(\w+)\s*=\s*\"__\(\s*'([^'\"]+?)'\s*\)\"",
		r'v-model:\1="\2"',
		text,
	)
	return text


# ── Tag content wrapping (opt-in for Button/etc inner text) ───────────────────

def wrap_tag_content(text: str, tag_names: Iterable[str]) -> str:
	"""Wrap simple text content inside specified tags with {{ __("text") }}.
	
	This wraps plain text between opening and closing tags like:
	  <Button>Send Invites</Button> -> <Button>{{ __("Send Invites") }}</Button>
	
	Safety guards:
	- Skip if already wrapped (contains {{ or __)
	- Skip if contains nested tags (< inside content)
	- Skip if tag has :label or label attribute (redundant)
	- Skip whitespace-only content
	- Trim leading/trailing whitespace from wrapped text
	
	Args:
		text: Vue template or component source
		tag_names: List of tag names to process (case-sensitive, e.g., ["Button"])
	
	Returns:
		Processed text with wrapped tag content
	"""
	if not tag_names:
		return text
	
	for tag_name in tag_names:
		# Pattern: <TagName ...> content </TagName>
		# Captures: opening tag, content, closing tag
		# Uses non-greedy match and excludes self-closing tags
		# Opening tag matcher that is safe for '>' inside quoted attribute values.
		# It matches any sequence of non-quote/gt OR quoted strings until the true closing '>'.
		opening_tag_re = rf"(<{re.escape(tag_name)}(?:[^>\"']|\"[^\"]*\"|'[^']*')*>)"
		pattern_str = (
			opening_tag_re  # opening tag
			+ rf"(.*?)"  # content (non-greedy)
			+ rf"(</{re.escape(tag_name)}>)"  # closing tag
		)
		pattern = re.compile(pattern_str, re.S)
		
		def _replacer(m: re.Match) -> str:
			opening, content, closing = m.group(1), m.group(2), m.group(3)
			
			# Skip if opening tag has :label or label attribute
			if re.search(r'(?::|^|\s)label\s*=', opening):
				return m.group(0)
			
			# Skip if content already has interpolation or wrapping
			if re.search(r'{{|}|__\s*\(', content):
				return m.group(0)
			
			# If content has nested tags, wrap ONLY the plain text segments between tags,
			# preserving all child tags as-is. Otherwise, treat the whole content as a single
			# text segment. This allows cases like:
			#   <p>Hello <a>world</a> !</p>
			# to become:
			#   <p>{{ __("Hello") }} <a>{{ __("world") }}</a> {{ __("!") }}</p>
			# while keeping attributes and structure intact.

			def _wrap_text_segment(seg: str) -> str:
				# Skip if already contains interpolation/wrapper
				if re.search(r"{{|}}|__\s*\(", seg):
					return seg
				# Preserve whitespace around the text segment
				leading_ws = seg[: len(seg) - len(seg.lstrip())]
				trailing_ws = seg[len(seg.rstrip()) :]
				trimmed = seg.strip()
				if not trimmed:
					return seg
				# Skip technical terms
				if _is_technical_term(trimmed):
					return seg
				# Collapse internal whitespace/newlines to a single space to avoid unterminated JS strings
				collapsed = re.sub(r"\s+", " ", trimmed)
				# Escape for JS string literal inside template interpolation
				safe_text = collapsed.replace("\\", "\\\\").replace('"', '\\"')
				return f"{leading_ws}{{{{ __(\"{safe_text}\") }}}}{trailing_ws}"

			if '<' in content:
				# Robustly tokenize by tags (respecting quotes inside tags) and wrap only plain text chunks
				def _split_by_tags(s: str) -> List[str]:
					parts: List[str] = []
					buf: List[str] = []
					in_tag = False
					quote: Optional[str] = None
					for ch in s:
						if in_tag:
							buf.append(ch)
							if quote:
								if ch == quote:
									quote = None
							else:
								if ch in ('"', "'"):
									quote = ch
								elif ch == '>':
									# end of tag
									parts.append(''.join(buf))
									buf = []
									in_tag = False
						else:
							if ch == '<':
								# flush text buffer
								if buf:
									parts.append(''.join(buf))
									buf = []
								in_tag = True
								buf.append(ch)
							else:
								buf.append(ch)
					# flush remainder
					if buf:
						parts.append(''.join(buf))
					return parts

				parts = _split_by_tags(content)
				# Guard: if there is no meaningful text (letters/digits) between tags, leave as-is
				if not any(part and not part.startswith('<') and re.search(r"[A-Za-z0-9]", part) for part in parts):
					return m.group(0)
				new_parts = []
				for part in parts:
					if not part:
						continue
					if part.startswith('<'):
						new_parts.append(part)
					else:
						new_parts.append(_wrap_text_segment(part))
				new_content = ''.join(new_parts)
				return f"{opening}{new_content}{closing}"

			# No nested tags: treat entire content as one segment
			return f"{opening}{_wrap_text_segment(content)}{closing}"
		
		text = pattern.sub(_replacer, text)
	
	return text


def wrap_toast_messages(text: str) -> str:
	"""Wrap toast.success() and toast.error() messages with __() for i18n.
	
	Converts:
		toast.success("Message") -> toast.success(__("Message"))
		toast.error("Error") -> toast.error(__("Error"))
	
	Safety guards:
		- Skip if already wrapped with __(
		- Skip if message is a variable/expression (contains ${ or starts with variable)
		- Skip template literals with interpolation
	
	Args:
		text: Vue or TypeScript source code
	
	Returns:
		Processed text with wrapped toast messages
	"""
	# Pattern to match toast.success("message") or toast.error("message")
	# but not already wrapped with __(
	pattern = r'toast\.(success|error)\((?!__\()(["\'])([^"\']*)\2'
	
	def _replacer(m: re.Match) -> str:
		method = m.group(1)  # success or error
		quote = m.group(2)   # " or '
		message = m.group(3)  # the message
		
		# Skip if message is empty
		if not message:
			return m.group(0)
		
		# Skip if message contains interpolation markers
		if '${' in message or message.startswith('${'):
			return m.group(0)
		
		# Skip if message appears to be a variable (no spaces, starts with lowercase/uppercase)
		# This catches cases like toast.success(successMessage)
		if ' ' not in message and not any(c in message for c in ['.', ',', '!', '?', ':']):
			# Likely a variable name, but we already filtered by quotes, so this is actual text
			pass
		
		return f'toast.{method}(__({quote}{message}{quote})'
	
	return re.sub(pattern, _replacer, text)


# ── Filesystem ops (atomic, reporting, ignore) ────────────────────────────────
@dataclasses.dataclass
class ProcessStats:
	scanned: int = 0
	changed: int = 0
	wrapped_strings: int = 0
	skipped_interpolations: int = 0


@dataclasses.dataclass
class WorkItem:
	path: pathlib.Path


def is_ignored(base: pathlib.Path, path: pathlib.Path, ignore_globs: List[str]) -> bool:
	try:
		rel = str(path.relative_to(base)).replace("\\", "/")
	except ValueError:
		return True
	return any(fnmatch.fnmatch(rel, pat) for pat in ignore_globs)


def atomic_write(path: pathlib.Path, data: str) -> None:
	"""Atomically write ``data`` to ``path``.

	This function writes to a temporary file in the same directory, fsyncs,
	then replaces the target. If the target exists, its permissions are
	preserved when possible.
	"""
	tmp_dir = path.parent
	# Ensure directory exists
	tmp_dir.mkdir(parents=True, exist_ok=True)
	# Capture original mode if present
	orig_mode = None
	try:
		st = path.stat()
	except OSError:
		st = None
	if st is not None:
		orig_mode = st.st_mode & 0o777

	tf = None
	try:
		with tempfile.NamedTemporaryFile("w", delete=False, dir=tmp_dir, encoding="utf-8", newline=NEWLINE) as tf:
			tf.write(data)
			tf.flush()
			os.fsync(tf.fileno())
			tmp_name = tf.name
		# Replace target atomically
		os.replace(tmp_name, str(path))
		# Restore permission bits when available
		if orig_mode is not None:
			try:
				os.chmod(str(path), orig_mode)
			except OSError:
				logger.debug("Failed to chmod %s", path)
	finally:
		# Cleanup if temp file still exists
		try:
			if tf is not None and os.path.exists(getattr(tf, 'name', '')):
				os.unlink(tf.name)
		except Exception:
			pass


def unified_diff(a: str, b: str, path: pathlib.Path) -> str:
	return "".join(
		difflib.unified_diff(
			a.splitlines(keepends=True),
			b.splitlines(keepends=True),
			fromfile=f"a/{path}",
			tofile=f"b/{path}",
		)
	)


# ── Main processing ──────────────────────────────────────────────────────────

def process_file(
	p: pathlib.Path,
	attr_keys: Iterable[str],
	js_keys: Iterable[str],
	dry: bool = False,
	no_backup: bool = False,
	enable_python: bool = False,
	py_cfg: Optional[PyWrapConfig] = None,
	emit_diff: bool = False,
	max_file_size: Optional[int] = None,
	normalize: bool = False,
	wrap_tags: Optional[Iterable[str]] = None,
	wrap_toast: bool = False,
) -> Tuple[int, Optional[str]]:
	# Safety checks: skip symlinks and very large files (configurable)
	try:
		if p.is_symlink():
			logger.warning("Skipping symlink: %s", p)
			return 0, None
	except OSError:
		logger.warning("Skipping path (is_symlink check failed): %s", p)
		return 0, None

	try:
		if max_file_size is not None and p.stat().st_size > max_file_size:
			logger.warning("Skipping large file (> %d bytes): %s", max_file_size, p)
			return 0, None
	except OSError:
		logger.warning("Skipping path (stat failed): %s", p)
		return 0, None

	try:
		text = p.read_text(encoding="utf-8")
		orig_text = text
	except (UnicodeDecodeError, OSError) as e:
		logger.warning("Failed to read %s: %s", p, e)
		return 0, None
	# Optional normalization of legacy wrapped calls (unescape bad backslashes)
	# Always perform a conservative normalization for front-end files to avoid
	# recurring escaped-quote artifacts that break build pipelines. This is
	# limited to .vue and .js/.ts files and is conservative (only unescapes
	# surrounding quotes inside __()). If the user passed --normalize we
	# already run a normalization; repeat is harmless.
	if p.suffix in (".vue", ".js", ".ts"):
		try:
			text = _normalize_wrapped(text)
		except Exception:
			logger.debug("Normalization failed for %s", p)
	elif normalize:
		# user explicitly asked to normalize other file types (e.g., .py)
		try:
			text = _normalize_wrapped(text)
		except Exception:
			logger.debug("Normalization failed for %s", p)
	new_text = text

	# Check if this is a Frappe doctype or report JS file
	# These files are loaded by Frappe framework and use global __ function
	# They should NOT have ES6 imports added
	path_str = str(p).replace('\\', '/')
	is_frappe_js = ('/doctype/' in path_str or '/report/' in path_str) and p.suffix in ('.js', '.ts')
	
	# CRITICAL: Skip JSON files entirely, especially DocType definitions
	# DocType JSON files contain database values (options, defaults, fieldnames) that MUST NOT be translated
	# Wrapping these values breaks validation and database operations
	if p.suffix == ".json":
		logger.debug("Skipping JSON file (contains database values): %s", p)
		return 0, None

	if p.suffix == ".vue":
		new_text = process_vue_file(text, attr_keys, js_keys, wrap_tags=wrap_tags, wrap_toast=wrap_toast)
	elif p.suffix in (".ts", ".js"):
		new_text = process_js_code(text, js_keys)
		# Also wrap toast messages in TypeScript/JavaScript files
		if wrap_toast:
			new_text = wrap_toast_messages(new_text)
		# Auto-inject import only when new __() calls were introduced
		if not is_frappe_js and new_text.count("__(") > text.count("__("):
			new_text = _inject_ts_import(new_text)
	elif enable_python and p.suffix == ".py":
		assert py_cfg is not None
		new_text = process_python_code(text, py_cfg)

	# Compare against the original on-disk content so that conservative
	# normalization (which updates `text` before processing) is detected and
	# written back when different from the original file.
	if new_text != orig_text:
		if dry:
			diff = unified_diff(text, new_text, p) if emit_diff else None
			return 1, diff
		else:
			if not no_backup:
				backup_name = f"{p.name}.{hashlib.sha1(text.encode('utf-8')).hexdigest()[:8]}.bak"
				backup_path = p.with_name(backup_name)
				try:
					# Preserve permissions for backup
					orig_mode = None
					try:
						orig_mode = p.stat().st_mode & 0o777
					except OSError:
						orig_mode = None
					atomic_write(backup_path, text)
					if orig_mode is not None:
						try:
							os.chmod(str(backup_path), orig_mode)
						except OSError:
							logger.debug("Failed to chmod backup %s", backup_path)
				except Exception as e:
					logger.warning("Could not write backup %s: %s", backup_path, e)
			# Write new contents atomically and try to preserve original mode
			try:
				orig_mode = None
				try:
					orig_mode = p.stat().st_mode & 0o777
				except OSError:
					orig_mode = None
				atomic_write(p, new_text)
				if orig_mode is not None:
					try:
						os.chmod(str(p), orig_mode)
					except OSError:
						logger.debug("Failed to chmod %s", p)
			except Exception as e:
				logger.error("Failed to write %s: %s", p, e)
				return 0, None
			return 1, None

	return 0, None


def discover_files(base: pathlib.Path, include_exts: Tuple[str, ...]) -> Iterable[pathlib.Path]:
	for ext in include_exts:
		yield from base.rglob(f"*{ext}")


# ── Missing translations reporter (scan codebase vs .po) ─────────────────────
def _unescape_literal(s: str) -> str:
	"""Best-effort unescape for string literal contents captured from code.

	We avoid ast.literal_eval to keep it lightweight and tolerant; unicode_escape
	handles standard escapes (\n, \t, \", \\). If decoding fails, return input.
	"""
	try:
		return bytes(s, "utf-8").decode("unicode_escape")
	except Exception:
		return s


def collect_wrapped_strings(
	base: pathlib.Path,
	include_exts: Tuple[str, ...] = (".vue", ".ts", ".js"),
	include_python: bool = False,
	ignore_globs: Optional[List[str]] = None,
) -> Tuple[set, int]:
	"""Scan files and collect unique strings wrapped for translation.

	Looks for __("...") and __('...') in Vue/JS/TS. If include_python is True,
	also collects _("") and frappe._("") from .py files.

	Returns (unique_set, total_matches_count)
	"""
	ignore_globs = ignore_globs or []

	# Frontend patterns for __("...") and __('...')
	re_js_dq = re.compile(r'__\(\s*"([^"\\]*(?:\\.[^"\\]*)*)"\s*\)')
	re_js_sq = re.compile(r"__\(\s*'([^'\\]*(?:\\.[^'\\]*)*)'\s*\)")

	# Python patterns for _("") and frappe._("") with single/double quotes
	re_py = re.compile(r"(?:frappe\._|_)\(\s*([\'\"])" r"([^\"\'\\]*(?:\\.[^\"\'\\]*)*)" r"\1\s*\)")

	unique: set = set()
	total = 0

	exts = include_exts + ((".py",) if include_python and ".py" not in include_exts else tuple())

	for p in discover_files(base, exts):
		try:
			if is_ignored(base, p, ignore_globs):
				continue
		except Exception:
			# If ignore calculation fails for any reason, do not skip the file blindly
			pass

		try:
			text = p.read_text(encoding="utf-8")
		except Exception:
			continue

		if p.suffix in (".vue", ".ts", ".js"):
			for m in re_js_dq.finditer(text):
				total += 1
				unique.add(_unescape_literal(m.group(1)))
			for m in re_js_sq.finditer(text):
				total += 1
				unique.add(_unescape_literal(m.group(1)))

		if include_python and p.suffix == ".py":
			for m in re_py.finditer(text):
				total += 1
				unique.add(_unescape_literal(m.group(2)))

	return unique, total


def parse_po_msgids(po_path: pathlib.Path) -> set:
	"""Parse a .po file and return a set of msgid strings.

	Handles multi-line msgid entries:
		msgid ""
		"part1"
		"part2"
	"""
	msgids: set = set()
	in_msgid = False
	cur_parts: List[str] = []

	def _flush():
		nonlocal cur_parts
		if cur_parts:
			val = _unescape_literal("".join(cur_parts))
			if val:
				msgids.add(val)
		cur_parts = []

	try:
		with po_path.open("r", encoding="utf-8") as f:
			for raw in f:
				line = raw.rstrip("\n")
				if line.startswith("msgid "):
					# finish previous
					if in_msgid:
						_flush()
					in_msgid = True
					# extract the first quoted segment after msgid
					m = re.match(r'^msgid\s+"(.*)"\s*$', line)
					cur_parts = [m.group(1) if m else ""]
					continue
				# Continuation lines of msgid
				if in_msgid and line.startswith('"'):
					m = re.match(r'^"(.*)"\s*$', line)
					if m:
						cur_parts.append(m.group(1))
					continue
				# end of msgid block on any other directive
				if in_msgid:
					_flush()
					in_msgid = False
			# EOF flush
			if in_msgid:
				_flush()
	except FileNotFoundError:
		raise
	except Exception as e:
		logger.error("Failed to parse .po file %s: %s", po_path, e)

	# Drop the header empty msgid if any
	msgids.discard("")
	return msgids


def report_missing_translations(
	base: pathlib.Path,
	po_path: pathlib.Path,
	include_python: bool = False,
	ignore_globs: Optional[List[str]] = None,
) -> int:
	"""Compare code-wrapped strings against .po msgids and print missing ones.

	Returns the count of missing msgids.
	"""
	unique, total = collect_wrapped_strings(
		base,
		include_exts=(".vue", ".ts", ".js"),
		include_python=include_python,
		ignore_globs=ignore_globs or [],
	)

	try:
		po_ids = parse_po_msgids(po_path)
	except FileNotFoundError:
		print(f".po file not found: {po_path}")
		return -1

	missing = sorted([s for s in unique if s not in po_ids])

	print(f"Scanned wrapped strings: {total} (unique: {len(unique)})")
	print(f"PO msgids in {po_path.name}: {len(po_ids)}")
	if not missing:
		print("All wrapped strings have entries in the .po file.")
		return 0

	print(f"Missing msgids ({len(missing)}):")
	for s in missing:
		print(s)
	return len(missing)


def append_missing_to_po(po_path: pathlib.Path, missing: Iterable[str]) -> None:
	"""Append missing msgids to a .po file with empty msgstr.

	Ensures entries are separated by blank lines and values are safely quoted.
	"""
	ts = datetime.datetime.now().isoformat(timespec="seconds")

	def _po_escape(s: str) -> str:
		return s.replace('\\', r'\\').replace('"', r'\"')

	lines: List[str] = []
	lines.append("")
	lines.append(f"# Auto-added by vue_i18n_wrap.py on {ts}")
	for s in missing:
		esc = _po_escape(s)
		lines.append(f'msgid "{esc}"')
		lines.append('msgstr ""')
		lines.append("")

	# Write append-only
	with po_path.open("a", encoding="utf-8") as f:
		f.write("\n".join(lines))


def run(args: argparse.Namespace) -> int:
	base = pathlib.Path(args.target).resolve()
	assert base.exists() and base.is_dir(), f"Target not found: {base}"

	attr_keys = [a.strip() for a in args.attrs.split(",") if a.strip()]
	js_keys = [a.strip() for a in args.js_keys.split(",") if a.strip()]

	ignore_globs = args.ignore or []

	# Optional mode: only report missing translations vs .po and exit
	if getattr(args, "check_missing_po", False):
		# Sensible defaults to avoid scanning vendor/build artifacts
		default_ignores = [
			"**/node_modules/**",
			"**/dist/**",
			"**/.git/**",
			"**/.cache/**",
			"**/.vite/**",
			"**/coverage/**",
			"**/build/**",
		]
		if not ignore_globs:
			ignore_globs = default_ignores
		else:
			# Append defaults if not already present
			ignore_globs = list({*ignore_globs, *default_ignores})
		po_path: Optional[pathlib.Path] = None
		if getattr(args, "po_file", None):
			p = pathlib.Path(args.po_file)
			if not p.is_absolute():
				# First try relative to base
				p2 = (base / p)
				po_path = p2 if p2.exists() else p
			else:
				po_path = p
		# Auto-discover tr.po if not provided or path does not exist
		if not po_path or not po_path.exists():
			candidates = list(base.rglob("locale/tr.po"))
			if candidates:
				po_path = candidates[0]
		if not po_path or not po_path.exists():
			print("Could not find tr.po. Pass --po-file PATH or run in a directory containing locale/tr.po")
			return 2

		# Compute and print missing, optionally append to PO
		unique, total = collect_wrapped_strings(
			base,
			include_exts=(".vue", ".ts", ".js"),
			include_python=getattr(args, "enable_python", False),
			ignore_globs=ignore_globs,
		)
		po_ids = parse_po_msgids(po_path)
		missing_list = sorted([s for s in unique if s not in po_ids])

		print(f"Scanned wrapped strings: {total} (unique: {len(unique)})")
		print(f"PO msgids in {po_path.name}: {len(po_ids)}")
		if not missing_list:
			print("All wrapped strings have entries in the .po file.")
			return 0

		print(f"Missing msgids ({len(missing_list)}):")
		for s in missing_list:
			print(s)

		if getattr(args, "write_missing_po", False):
			append_missing_to_po(po_path, missing_list)
			print(f"\nAppended {len(missing_list)} skeleton entries to: {po_path}")

		return 0

	include_exts: Tuple[str, ...] = (".vue", ".ts", ".js")
	if args.enable_python:
		include_exts = include_exts + (".py",)

	py_cfg = None
	if args.enable_python:
		py_keys = tuple([a.strip() for a in args.py_keys.split(",") if a.strip()]) or ("label",)
		py_cfg = PyWrapConfig(func=args.py_func, qualify="frappe._", keys=py_keys, inject_import=not args.no_import_inject)

	files = list(discover_files(base, include_exts))

	changed = 0
	diffs: List[str] = []

	wrap_tags = None
	if hasattr(args, 'wrap_tag_content') and args.wrap_tag_content:
		wrap_tags = tuple([t.strip() for t in args.wrap_tag_content.split(",") if t.strip()])

	wrap_toast = getattr(args, 'wrap_toast', False)

	def _work(p: pathlib.Path):
		try:
			if is_ignored(base, p, ignore_globs):
				return 0, None
			return process_file(
				p,
				attr_keys,
				js_keys,
				dry=args.dry_run,
				no_backup=args.no_backup,
				enable_python=args.enable_python,
				py_cfg=py_cfg,
				emit_diff=args.diff,
				max_file_size=getattr(args, 'max_file_size', None),
				normalize=getattr(args, 'normalize', False),
				wrap_tags=wrap_tags,
				wrap_toast=wrap_toast,
			)
		except Exception as e:
			# Log and continue other files — robust against single-file failures
			logger.error("Error processing %s: %s", p, e)
			return 0, None

	# Threaded I/O for speed
	with cf.ThreadPoolExecutor(max_workers=max(1, args.threads)) as ex:
		for c, d in ex.map(_work, files):
			changed += c
			if d:
				diffs.append(d)

	if args.diff and diffs:
		sys.stdout.write("\n".join(d for d in diffs if d))

	print(f"\nDone. Files changed: {changed}")
	return 0


def build_arg_parser() -> argparse.ArgumentParser:
	ap = argparse.ArgumentParser()
	ap.add_argument("--target", required=True, help="Scan root directory (e.g., apps/helpdesk/desk/src or apps/helpdesk/helpdesk)")
	ap.add_argument("--attrs", default="label,title,placeholder,tooltip,aria-label,description", help="Template attributes (comma-separated)")
	ap.add_argument("--js-keys", default="label,title,placeholder,tooltip,aria-label,ariaLabel,description", help="Script-side property keys (comma-separated)")
	ap.add_argument("--dry-run", action="store_true", help="Report only; no writes")
	ap.add_argument("--no-backup", action="store_true", help="Do not write .bak backups")
	ap.add_argument("--ignore", action="append", default=[], help="Glob patterns to exclude (repeatable)")
	ap.add_argument("--threads", type=int, default=os.cpu_count() or 4, help="Parallel file workers")
	ap.add_argument("--diff", action="store_true", help="Print unified diff for changes (with --dry-run)")
	ap.add_argument("--max-file-size", type=int, default=2*1024*1024, help="Skip files larger than this many bytes (0 to disable)")
	ap.add_argument("--normalize", action="store_true", help="Normalize previously malformed wrapped calls (unescape legacy backslashes)")

	# Python support (opt-in)
	ap.add_argument("--enable-python", action="store_true", help="Enable Python (.py) wrapping for Doctype dict labels")
	ap.add_argument("--py-keys", default="label", help="Python dict keys to wrap (comma-separated)")
	ap.add_argument("--py-func", default="_", help="Python i18n function name (default: _)")
	ap.add_argument("--no-import-inject", action="store_true", help="Do not auto-inject `from frappe import _` when needed")

	# Tag content wrapping (opt-in for Button/etc)
	ap.add_argument("--wrap-tag-content", metavar="TAGS", help="Wrap inner text of specified tags with {{ __(\"text\") }} (comma-separated, e.g., Button,CustomButton)")
	
	# Toast message wrapping
	ap.add_argument("--wrap-toast", action="store_true", help="Wrap toast.success() and toast.error() messages with __()")

	# Missing translations reporter
	ap.add_argument("--check-missing-po", action="store_true", help="Only scan and compare wrapped strings to .po (no writes)")
	ap.add_argument("--po-file", help="Path to the .po file to compare against (defaults to first locale/tr.po under --target)")
	ap.add_argument("--write-missing-po", action="store_true", help="Append missing msgids with empty msgstr to the given .po file")

	return ap


def main():
	args = build_arg_parser().parse_args()
	sys.exit(run(args))


if __name__ == "__main__":
	main()
