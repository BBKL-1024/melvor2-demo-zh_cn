extends Node

# Melvor2 Chinese patch -- GDScript build (zero-touch).
#
# HOW IT GETS CALLED
#   `override.cfg` next to Melvor2.exe declares
#       [autoload]
#       ZhPatch="*res://mod/zhpatch.gd"
#   Godot's ProjectSettings::_setup() reads that file for every exported project,
#   whether the pck is embedded in the exe or sits next to it, so the engine itself
#   registers this script as an autoload singleton at start-up. No game file is
#   modified, nothing is injected, no dll is rewritten.
#
#   override.cfg is the only file that cannot live in the mod folder: Godot looks for it
#   at a fixed path beside the executable. Everything else, this script included, stays
#   under mod/ so the game folder gains one file and one directory.
#
# WHY THE GAME STILL GOES CHINESE
#   The English source string *is* the gettext key: LocalizedString.Text delegates to
#   TranslationServer.Translate(englishString). So a catalog that maps
#   "Bank" -> "库存" answers the lookup no matter which locale id the game pins.
#   The engine locale deliberately stays "en_GB" -- the id the game itself sets -- and
#   the language is a single boolean: is our catalog mounted or not?
#
#       mounted  -> Translate("Bank") finds a message -> Chinese
#       detached -> nothing found, Godot returns the key, and the key IS the English
#                   source -> English, with no English catalog needed
#
#   Switching the locale id instead does NOT work and was measured on the C# build:
#   SetLocale("zh_CN") is accepted, GetLocale() reports "zh_CN", and Translate("Bank")
#   still returns "Bank". Hence this design.
#
# PERSISTENCE
#   mod/language.cfg, one line: "language=zh_CN" or "language=en_GB".
#   The MELVOR2_ZH_LANG environment variable overrides it (diagnostics only).
#
# Every step is logged to mod/zhpatch.log. Nothing here may throw into the game's boot
# sequence, so every stage is individually guarded.

# ---------------------------------------------------------------- constants

const CHINESE := "zh_CN"
const ENGLISH := "en_GB"

const LANGUAGE_FILE := "language.cfg"
const LANGUAGE_ENV := "MELVOR2_ZH_LANG"
const MOD_DIR := "mod"
const PO_NAME := "zh_CN.po"
const PO_ENV := "MELVOR2_ZH_PO"
const LOG_NAME := "zhpatch.log"
const SESSION_MARKER := "Melvor2 ZhPatch (GDScript) starting"
const LOG_SESSIONS_TO_KEEP := 3

# Set MELVOR2_ZH_VERBOSE=1 to log every node the wrap fix rewrites. Off by default:
# the scan touches hundreds of nodes twice a second and would bury the log.
const VERBOSE_ENV := "MELVOR2_ZH_VERBOSE"

const QUEST_DIALOGUE_ROOT := "QuestDialogueView"
const WRAP_SCAN_INTERVAL := 120          # frames, ~2x per second at 60fps
const SETTINGS_SWEEP_FRAMES := 600       # frames, ~10s; safety net if node_added never fires

# Same candidate order as the C# build: DengXian first because it is a single-face TTF
# with full CJK coverage (msyh/simsun are collections and load slower).
const FONT_CANDIDATES := [
	"C:/Windows/Fonts/Deng.ttf",
	"C:/Windows/Fonts/msyh.ttc",
	"C:/Windows/Fonts/simhei.ttf",
	"C:/Windows/Fonts/msyhbd.ttc",
	"C:/Windows/Fonts/simkai.ttf",
	"C:/Windows/Fonts/simsun.ttc",
]

# Control types whose theme font gets the CJK font grafted on as a fallback. ThemeDB's
# fallback alone is not enough: the game's own theme resolves a font for each of these
# and that font has no CJK glyphs.
const THEME_TYPES := [
	"Label", "RichTextLabel", "Button", "CheckBox", "CheckButton", "LineEdit",
	"OptionButton", "PopupMenu", "TooltipLabel", "Tree", "ItemList", "TabBar",
]

# ---------------------------------------------------------------- state

var _base_dir := ""
var _log_path := ""
var _verbose := false

var _language := CHINESE
var _zh_catalog: Translation = null
var _mounted := false
var _switchable := false
var _catalog_map: Dictionary = {}
var _probe_key := ""
var _probe_value := ""

var _game_catalogs: Array[Translation] = []

var _wrap_tick := 0
var _settings_tick := 0
var _settings_hooked := false
var _settings_found := false
var _cjk_font: Font = null

# Diagnostic screenshot state (see _requested_shot_path).
const SHOT_DELAY_FRAMES := 360
var _shot_path := ""
var _shot_frames := SHOT_DELAY_FRAMES
var _switch_test_pending := false
var _switch_test_frames := SHOT_DELAY_FRAMES

# ---------------------------------------------------------------- boot

func _ready() -> void:
	_base_dir = OS.get_executable_path().get_base_dir()
	_log_path = _pick_log_path()
	_verbose = OS.get_environment(VERBOSE_ENV) == "1"

	_trim_old_sessions()
	_log("==================================================")
	_log(SESSION_MARKER)
	_log("script dir   : %s" % _base_dir)
	_log("mod dir      : %s" % _base_dir.path_join(MOD_DIR))
	_log("engine locale before: %s" % TranslationServer.get_locale())

	_load_catalog()
	_install_font()

	var wanted := _read_requested_language()
	_log("requested language: %s  (from %s)" % [wanted, _language_source()])
	_activate_language(wanted, false, false)

	_install_settings_hook()
	set_process(true)

	_log("ZhPatch done (switchable=%s, language=%s, engine locale=%s)"
		% [_switchable, _language, TranslationServer.get_locale()])
	_log("==================================================")

	# Diagnostic hook: grab one frame a few seconds in. Accepts an environment variable or
	# a user command-line argument (`Melvor2.exe -- --zh-shot=<abs png path>`), so the
	# patch can be verified without touching this file. Never active during a normal launch.
	_shot_path = _requested_shot_path()
	_log("diagnostic shot request: '%s'" % _shot_path)

	for arg in OS.get_cmdline_user_args():
		if arg == "--zh-test-switch":
			_switch_test_pending = true
			_log("switch test: queued")

func _requested_shot_path() -> String:
	var from_env := OS.get_environment("MELVOR2_ZH_SHOT").strip_edges()
	if from_env != "":
		return from_env
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--zh-shot="):
			return arg.substr(10).strip_edges()
	return ""

func _do_shot() -> void:
	var img := get_viewport().get_texture().get_image()
	if img == null:
		_log("diagnostic screenshot: no viewport image")
		return
	var err := img.save_png(_shot_path)
	_log("diagnostic screenshot -> %s (err=%d)" % [_shot_path, err])

func _run_switch_test() -> void:
	_log("switch test: begin (probe key '%s')" % _probe_key)
	_log("switch test: before   translate='%s' cfg='%s'"
		% [TranslationServer.translate(_probe_key), _read_requested_language()])

	var to_english := set_language(ENGLISH)
	_log("switch test: to en_GB -> %s | translate='%s' | cfg='%s'"
		% [to_english, TranslationServer.translate(_probe_key), _read_requested_language()])

	var to_chinese := set_language(CHINESE)
	_log("switch test: to zh_CN -> %s | translate='%s' | cfg='%s'"
		% [to_chinese, TranslationServer.translate(_probe_key), _read_requested_language()])

	_log("switch test: done (switchable=%s)" % _switchable)

# ------------------------------------------------------------ language logic

func _is_chinese(locale: String) -> bool:
	return locale.to_lower().begins_with("zh")

func _activate_language(locale: String, persist: bool, broadcast: bool) -> bool:
	var want_chinese := _is_chinese(locale)

	# The engine locale is pinned, never switched. Setting it here just makes the session
	# deterministic: before the game's own SetLocale("en_GB") runs, the engine reports
	# whatever the OS says (zh_CN on this machine).
	TranslationServer.set_locale(ENGLISH)
	_log("engine locale: '%s' (pinned) | requested: %s"
		% [TranslationServer.get_locale(), CHINESE if want_chinese else ENGLISH])

	if not _set_catalog_mounted(want_chinese, broadcast):
		return false

	_language = CHINESE if want_chinese else ENGLISH
	_switchable = true

	# Both directions must be provable, or the dropdown would be a lie.
	var served := _probe(want_chinese)
	if not served:
		_log("WARN %s is not being served as expected; reverting" % _language)
		_set_catalog_mounted(not want_chinese, broadcast)
		_language = ENGLISH if want_chinese else CHINESE
		_switchable = false
		return false

	# Boot only: exercise the other direction once, before the player can click anything.
	if not persist:
		var other := _probe_other_direction(want_chinese)
		var restored := _probe(want_chinese)
		_switchable = other and restored
		_log("self test: other direction %s | after restore %s -> switchable=%s"
			% ["ok" if other else "FAILED", "ok" if restored else "FAILED", _switchable])

	if persist:
		_write_requested_language(_language)

	return true

func _probe_other_direction(chinese_active: bool) -> bool:
	var saved := _mounted
	var ok := false
	if _set_catalog_mounted(not chinese_active, false):
		ok = _probe(not chinese_active)
	_set_catalog_mounted(saved, false)
	return ok

# <summary>
# Mounts or detaches the Chinese catalog. This is the whole language switch: the catalog
# is registered under the game's own locale, so what decides the language is simply
# whether it is in the engine's translation list.
# </summary>
func _set_catalog_mounted(mounted: bool, broadcast: bool) -> bool:
	if _zh_catalog == null:
		_log("no catalog registered -- language cannot be changed")
		return false

	if mounted == _mounted:
		return true

	if mounted:
		TranslationServer.add_translation(_zh_catalog)

		# Ours should be the only en_GB catalog while Chinese is on: Godot walks the list
		# in insertion order and the game's own copy would answer first for whatever
		# handful of strings it carries.
		_hide_game_catalogs()
	else:
		TranslationServer.remove_translation(_zh_catalog)

		# English mode: give the game back everything it shipped with, so nothing that
		# only existed in its catalog turns into a raw key.
		_restore_game_catalogs()

	_mounted = mounted
	_log("catalog %s -> %s" % ["mounted" if mounted else "detached",
		"Chinese" if mounted else "English"])

	if broadcast:
		_broadcast_translation_changed()

	return true

func _probe(want_chinese: bool) -> bool:
	# The two directions are not symmetric, so each gets its own expectation:
	#   catalog mounted   -> translate(key) returns the Chinese message
	#   catalog detached  -> nothing matches and Godot hands back the key itself,
	#                        which IS the English source string
	if _probe_key == "":
		return false
	var got := String(TranslationServer.translate(_probe_key))
	if want_chinese:
		return got == _probe_value and got != _probe_key
	return got == _probe_key

func _broadcast_translation_changed() -> void:
	# NOTIFICATION_TRANSLATION_CHANGED (2010) is what the game's own localized labels
	# listen for; a manual broadcast is the only way to repaint after a catalog swap.
	var tree := get_tree()
	if tree != null and tree.root != null:
		tree.root.propagate_notification(NOTIFICATION_TRANSLATION_CHANGED)

func set_language(locale: String) -> bool:
	if not _switchable:
		_log("set_language('%s') refused: switching unavailable" % locale)
		return false
	var ok := _activate_language(locale, true, true)
	if ok:
		_sync_dropdowns()
	return ok

func toggle_language_temporarily() -> bool:
	if not _switchable:
		return false
	var target := ENGLISH if _is_chinese(_language) else CHINESE
	var ok := _activate_language(target, false, true)
	if ok:
		_sync_dropdowns()
	return ok

# ---------------------------------------------------------------- catalog

# The catalog lives inside the mod folder so the game directory only ever gains one
# file (override.cfg, which Godot insists on reading from the exe folder) and one
# directory. A catalog dropped straight into the game folder is still honoured, which
# keeps deployments made with the older flat layout working.
func _find_catalog() -> String:
	var nested := _base_dir.path_join(MOD_DIR).path_join(PO_NAME)
	if FileAccess.file_exists(nested):
		return nested
	var flat := _base_dir.path_join(PO_NAME)
	if FileAccess.file_exists(flat):
		return flat
	return nested

func _load_catalog() -> void:
	var po_path := OS.get_environment(PO_ENV)
	if po_path == "":
		po_path = _find_catalog()

	if not FileAccess.file_exists(po_path):
		_log("CATALOG MISSING: %s" % po_path)
		return

	var text := ""
	var f := FileAccess.open(po_path, FileAccess.READ)
	if f == null:
		_log("PO open failed: %s" % po_path)
		return
	text = f.get_as_text()
	f.close()

	_catalog_map = _parse_po(text)
	_log("po entries parsed: %d  (%s)" % [_catalog_map.size(), po_path])

	if _catalog_map.is_empty():
		return

	# The self test needs one key that is definitely routed through a plain Translate()
	# call, so known UI words are tried first. Very short keys like "-s" are rejected:
	# they collide with formatting fragments and prove little about the catalog.
	var known := ["Bank", "Attack", "Settings", "Woodcutting", "Combat", "Total Level"]
	for known_key in known:
		if _catalog_map.has(known_key):
			var known_val: String = _catalog_map[known_key]
			if known_val != "" and known_val != known_key:
				_probe_key = known_key
				_probe_value = known_val
				break

	if _probe_key == "":
		for any_key in _catalog_map.keys():
			var any_val: String = _catalog_map[any_key]
			if any_val == "" or any_val == any_key:
				continue
			if any_key.length() < 3 or any_key.length() > 24:
				continue
			if any_key.begins_with("-") or any_key.contains("{"):
				continue
			_probe_key = any_key
			_probe_value = any_val
			break

	_log("probe key: '%s' -> '%s'" % [_probe_key, _probe_value])

	_zh_catalog = _register_catalog(ENGLISH)
	_mounted = _zh_catalog != null
	_hide_game_catalogs()

func _register_catalog(locale: String) -> Translation:
	var t := Translation.new()
	t.locale = locale

	var added := 0
	var skipped_empty := 0
	var skipped_same := 0

	for k in _catalog_map.keys():
		var v: String = _catalog_map[k]
		if k == "":
			continue                     # PO header
		if v == "":
			skipped_empty += 1
			continue
		if v == k:
			skipped_same += 1
			continue

		t.add_message(k, v)

		# Data-pack names are PluralString, and both their Text and their count-aware
		# path reach Godot through TranslatePlural -- which looks in the catalog's plural
		# map, not its message map. A catalog built with add_message alone therefore
		# answers Translate() but NOT TranslatePlural(), and everything routed through
		# PluralString stays English: item names, monster names, "+3 x something" lines.
		# Chinese has one plural form, so a single entry covers every count.
		t.add_plural_message(k, PackedStringArray([v]))

		added += 1

	TranslationServer.add_translation(t)
	_log("messages added: %d (%s) | skipped empty: %d | skipped identical: %d"
		% [added, locale, skipped_empty, skipped_same])
	return t

func _hide_game_catalogs() -> void:
	# TranslationServer.get_translations() is not part of the documented GDScript API on
	# every 4.x build, so this is best-effort: if the method is missing we simply skip it.
	# Measured on 4.7.2: the game ships no en_GB catalog of its own, so skipping is safe.
	if not TranslationServer.has_method("get_translations"):
		return

	var hidden := 0
	for t in TranslationServer.get_translations():
		if t == null or t == _zh_catalog:
			continue
		if t.locale != ENGLISH:
			continue
		TranslationServer.remove_translation(t)
		hidden += 1
		if not _game_catalogs.has(t):
			_game_catalogs.append(t)

	if hidden > 0:
		_log("hid %d game catalog(s) for %s (kept for English mode)" % [hidden, ENGLISH])

func _restore_game_catalogs() -> void:
	for t in _game_catalogs:
		if t != null:
			TranslationServer.add_translation(t)

# ---------------------------------------------------------------- po parsing

func _parse_po(text: String) -> Dictionary:
	var map := {}
	var msgid := ""
	var msgstr := ""
	var in_msgstr := false
	var has_entry := false

	for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
		var line := String(raw).strip_edges()
		if line == "" or line.begins_with("#"):
			continue

		if line.begins_with("msgid "):
			if has_entry:
				_commit(map, msgid, msgstr)
			msgid = _unquote(line.substr(6))
			msgstr = ""
			in_msgstr = false
			has_entry = true
		elif line.begins_with("msgstr "):
			msgstr = _unquote(line.substr(7))
			in_msgstr = true
		elif line.begins_with("\"") and has_entry:
			if in_msgstr:
				msgstr += _unquote(line)
			else:
				msgid += _unquote(line)

	if has_entry:
		_commit(map, msgid, msgstr)

	return map

func _commit(map: Dictionary, msgid: String, msgstr: String) -> void:
	if msgid == "":
		return
	map[msgid] = msgstr

func _unquote(s: String) -> String:
	s = s.strip_edges()
	if s.length() >= 2 and s.begins_with("\"") and s.ends_with("\""):
		s = s.substr(1, s.length() - 2)

	if not s.contains("\\"):
		return s

	var out := ""
	var i := 0
	while i < s.length():
		var c := s[i]
		if c != "\\" or i + 1 >= s.length():
			out += c
			i += 1
			continue
		var n := s[i + 1]
		match n:
			"n": out += "\n"
			"r": out += "\r"
			"t": out += "\t"
			"\"": out += "\""
			"\\": out += "\\"
			_: out += c
		i += 2
	return out

# ---------------------------------------------------------------- fonts

func _install_font() -> void:
	for path in FONT_CANDIDATES:
		if not FileAccess.file_exists(path):
			continue
		var ff := FontFile.new()
		var err := ff.load_dynamic_font(path)
		if err != OK:
			_log("FONT load %s -> error %d" % [path, err])
			continue

		_cjk_font = ff
		ThemeDB.fallback_font = ff
		_log("FONT loaded %s (set as ThemeDB.fallback_font)" % path)

		var patched := 0
		patched += _patch_theme(ThemeDB.get_project_theme(), ff, "project")
		patched += _patch_theme(ThemeDB.get_default_theme(), ff, "default")
		_log("FONT fallbacks grafted onto %d font(s)" % patched)
		return

	# Last resort: let Godot resolve a system font by family name.
	_log("FONT: no CJK font file found, trying SystemFont")
	var sys := SystemFont.new()
	sys.font_names = PackedStringArray(["Microsoft YaHei", "DengXian", "SimHei"])
	_cjk_font = sys
	ThemeDB.fallback_font = sys
	_patch_theme(ThemeDB.get_project_theme(), sys, "project")
	_patch_theme(ThemeDB.get_default_theme(), sys, "default")
	_log("FONT: SystemFont fallback installed")

func _patch_theme(theme: Theme, cjk: Font, label: String) -> int:
	if theme == null:
		return 0

	var count := 0
	var df := theme.default_font
	if df != null and _append_fallback(df, cjk):
		count += 1

	for type_name in THEME_TYPES:
		var f := theme.get_font("font", type_name)
		if f != null and _append_fallback(f, cjk):
			count += 1

	_log("FONT theme '%s': %d font(s) patched" % [label, count])
	return count

func _append_fallback(target: Font, extra: Font) -> bool:
	var arr := target.fallbacks
	if arr == null:
		arr = []
	for e in arr:
		if e == extra:
			return false
	arr.append(extra)
	target.fallbacks = arr
	return true

# -------------------------------------------------- in-game language dropdown

func _install_settings_hook() -> void:
	if _settings_hooked:
		return
	if not _switchable:
		_log("settings hook: switching unavailable, dropdown not installed")
		return

	var tree := get_tree()
	if tree == null:
		_log("settings hook: no SceneTree -- in-game dropdown unavailable")
		return

	if not tree.node_added.is_connected(_on_node_added):
		tree.node_added.connect(_on_node_added)
	_settings_hooked = true
	_log("settings hook: node_added subscribed")

	# A pre-built settings scene may already be in the tree and never raise node_added
	# again, so sweep once as well.
	call_deferred("_sweep_settings")

func _on_node_added(node: Node) -> void:
	if _is_settings_view(node):
		_inject_language_row(node)

func _sweep_settings() -> void:
	var tree := get_tree()
	if tree == null or tree.root == null:
		return
	var found := 0
	for node in tree.root.find_children("*", "", true, false):
		if _is_settings_view(node):
			_inject_language_row(node)
			found += 1
	if found > 0:
		_settings_found = true
		_log("settings sweep: %d InterfaceSettingsView node(s) scanned" % found)

func _is_settings_view(node: Node) -> bool:
	var script := node.get_script()
	if script == null:
		return false
	var path: String = script.resource_path
	if path == "":
		return false
	var lower := path.to_lower()
	return lower.ends_with("interfacesettingsview.cs") \
		or lower.ends_with("interface_settings_view.cs") \
		or lower.ends_with("interfacesettingsview.gd")

func _inject_language_row(node: Node) -> void:
	if not (node is VBoxContainer):
		_log("language row: %s is not a VBoxContainer, skipped" % node.get_class())
		return

	var box := node as VBoxContainer
	if box.has_node("ZhLanguageRow"):
		return

	var row := HBoxContainer.new()
	row.name = "ZhLanguageRow"
	row.add_theme_constant_override("separation", 12)

	var label := Label.new()
	label.name = "ZhLanguageLabel"
	# Bilingual and fixed on purpose: the label needs no update when the language
	# changes, which removes a whole class of stale-text bugs.
	label.text = "语言 / Language"
	label.auto_translate_mode = Node.AUTO_TRANSLATE_MODE_DISABLED
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	row.add_child(label)

	var opt := OptionButton.new()
	opt.name = "ZhLanguageOption"
	opt.auto_translate_mode = Node.AUTO_TRANSLATE_MODE_DISABLED
	opt.custom_minimum_size = Vector2(190, 0)
	opt.add_item("简体中文", 0)
	opt.add_item("English", 1)
	opt.selected = 0 if _is_chinese(_language) else 1
	opt.item_selected.connect(_on_language_item_selected)
	row.add_child(opt)

	box.add_child(row)
	box.move_child(row, 0)
	_settings_found = true
	_log("language dropdown injected at %s/ZhLanguageRow" % box.get_path())

func _on_language_item_selected(index: int) -> void:
	var target := CHINESE if index == 0 else ENGLISH
	_log("dropdown selected index %d -> %s" % [index, target])
	# Deferred on purpose: swapping the catalog makes Godot repaint the whole tree, and
	# doing that from inside a dropdown signal re-enters the control still handling the
	# click.
	call_deferred("set_language", target)

func _sync_dropdowns() -> void:
	var tree := get_tree()
	if tree == null or tree.root == null:
		return
	var wanted := 0 if _is_chinese(_language) else 1
	for node in tree.root.find_children("ZhLanguageOption", "", true, false):
		if node is OptionButton and (node as OptionButton).selected != wanted:
			(node as OptionButton).selected = wanted

# ---------------------------------------------------------------- per-frame

func _process(_delta: float) -> void:
	# Diagnostic screenshot, counted in frames so it cannot be missed by a paused tree.
	if _shot_path != "":
		_shot_frames -= 1
		if _shot_frames <= 0:
			_do_shot()
			_shot_path = ""

	# Diagnostic round trip through the real switch path (catalog mount/unmount, the
	# broadcast, language.cfg persistence and dropdown sync) without clicking anything.
	if _switch_test_pending:
		_switch_test_frames -= 1
		if _switch_test_frames <= 0:
			_switch_test_pending = false
			_run_switch_test()

	# The settings page may be built from an already-instantiated scene that never raises
	# node_added. Sweeping every 10s costs nothing once the row has been injected; the
	# flag stops the walk entirely after the first hit.
	if not _settings_found and _switchable:
		_settings_tick = (_settings_tick + 1) % SETTINGS_SWEEP_FRAMES
		if _settings_tick == 0:
			_sweep_settings()

	_wrap_tick = (_wrap_tick + 1) % WRAP_SCAN_INTERVAL
	if _wrap_tick != 0:
		return
	if not _is_chinese(_language):
		return
	var tree2 := get_tree()
	if tree2 != null and tree2.root != null:
		_scan_wrap(tree2.root, 0, false)

# ------------------------------------------------------------- autowrap fix

# WordSmart is a superset of Word: English keeps breaking on spaces exactly as before,
# Chinese gains break points between characters. That is why switching back to English
# needs no restore step -- the promoted mode already behaves like the original.
#
# The C# build also rewrote every `AutowrapMode = Word` assignment in the assembly at
# install time (patch 8). This build has no assembly to rewrite, so the whole job is the
# runtime pass, which also reaches labels whose mode comes from the scene export.
func _scan_wrap(node: Node, depth: int, in_quest: bool) -> void:
	if node == null or depth > 40:
		return

	if not in_quest and node.name == QUEST_DIALOGUE_ROOT:
		in_quest = true

	_inspect_wrap(node, in_quest)

	for i in node.get_child_count():
		_scan_wrap(node.get_child(i), depth + 1, in_quest)

func _inspect_wrap(node: Node, in_quest: bool) -> void:
	if node is RichTextLabel:
		var rich := node as RichTextLabel
		var rewrap := rich.autowrap_mode == TextServer.AUTOWRAP_WORD
		# Wrapping turns one long line into several; a label that refuses to grow simply
		# clips the extra lines instead, so the quest page has to be allowed to expand.
		var regrow := in_quest and not rich.fit_content

		if rewrap:
			rich.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		if regrow:
			rich.fit_content = true

		if _verbose and (rewrap or regrow):
			_log("wrap: %s [%s]%s%s" % [node.get_path(), node.get_class(),
				" word->smart" if rewrap else "", " fit=false->true" if regrow else ""])
		return

	if node is Label and (node as Label).autowrap_mode == TextServer.AUTOWRAP_WORD:
		# Word was an explicit choice here, so it would have clipped English too once the
		# text grew. Promote it; leave Off alone, it means "single line on purpose".
		(node as Label).autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		if _verbose:
			_log("wrap: %s [Label] word->smart" % node.get_path())

# ------------------------------------------------------------------ hotkey

func _input(event: InputEvent) -> void:
	if not (event is InputEventKey):
		return
	var key := event as InputEventKey
	if not key.pressed or key.echo:
		return
	if key.ctrl_pressed and key.keycode == KEY_T:
		if toggle_language_temporarily():
			_log("hotkey: toggled to %s (not saved)" % _language)

# --------------------------------------------------------------- persistence

func _read_requested_language() -> String:
	var env := OS.get_environment(LANGUAGE_ENV).strip_edges()
	if env != "":
		return env

	var f := FileAccess.open(_path_in_mod(LANGUAGE_FILE), FileAccess.READ)
	if f == null:
		return CHINESE

	var value := ""
	while not f.eof_reached():
		var line := f.get_line().strip_edges()
		if line.begins_with("language="):
			value = line.substr(9).strip_edges()
	f.close()
	return value if value != "" else CHINESE

func _write_requested_language(locale: String) -> void:
	var f := FileAccess.open(_path_in_mod(LANGUAGE_FILE), FileAccess.WRITE)
	if f == null:
		_log("language.cfg write failed: %s" % _path_in_mod(LANGUAGE_FILE))
		return
	f.store_string("# Melvor Idle 2 Chinese patch -- language chosen in-game.\n")
	f.store_string("# zh_CN = 简体中文 / Simplified Chinese\n")
	f.store_string("# en_GB = English\n")
	f.store_string("language=%s\n" % locale)
	f.close()

func _language_source() -> String:
	if OS.get_environment(LANGUAGE_ENV).strip_edges() != "":
		return "env " + LANGUAGE_ENV
	if FileAccess.file_exists(_path_in_mod(LANGUAGE_FILE)):
		return MOD_DIR + "/" + LANGUAGE_FILE
	return "default"

# --------------------------------------------------------------------- log

# Everything the patch owns lives under mod/, including the two files it generates at
# runtime (language.cfg and zhpatch.log), so installing it adds exactly one file and one
# directory to the game folder. The directory is created on demand because a player may
# have copied override.cfg across before the folder.
func _path_in_mod(name: String) -> String:
	var dir := _base_dir.path_join(MOD_DIR)
	if not DirAccess.dir_exists_absolute(dir):
		DirAccess.make_dir_recursive_absolute(dir)
	return dir.path_join(name)

func _pick_log_path() -> String:
	# Lives beside the patch in mod/, which is where a user looking for "why did it
	# break" will look next. Fall back to user:// when the install sits somewhere
	# read-only (Program Files), because a failed write must never stop the patch from
	# loading.
	var candidate := _path_in_mod(LOG_NAME)
	var probe := FileAccess.open(candidate, FileAccess.WRITE)
	if probe != null:
		probe.close()
		return candidate
	return "user://" + LOG_NAME

func _log(message: String) -> void:
	var line := "[%s] %s" % [Time.get_datetime_string_from_system(false, true), message]
	var f := FileAccess.open(_log_path, FileAccess.READ_WRITE)
	if f == null:
		f = FileAccess.open(_log_path, FileAccess.WRITE)
	if f == null:
		return
	f.seek_end()
	f.store_string(line + "\n")
	f.close()

func _trim_old_sessions() -> void:
	if _log_path == "" or not FileAccess.file_exists(_log_path):
		return

	var f := FileAccess.open(_log_path, FileAccess.READ)
	if f == null:
		return
	var lines := PackedStringArray()
	while not f.eof_reached():
		lines.append(f.get_line())
	f.close()

	var starts: Array[int] = []
	for i in lines.size():
		if lines[i].contains(SESSION_MARKER):
			starts.append(i)

	# One of the sessions we are allowed to keep is the one starting right now.
	var allowed_previous := LOG_SESSIONS_TO_KEEP - 1
	if starts.size() <= allowed_previous:
		return

	var from: int = starts[starts.size() - allowed_previous]
	if from > 0 and lines[from - 1].contains("===="):
		from -= 1

	var kept := PackedStringArray()
	for i in range(from, lines.size()):
		kept.append(lines[i])

	var w := FileAccess.open(_log_path, FileAccess.WRITE)
	if w == null:
		return
	w.store_string("\n".join(kept) + "\n")
	w.close()
