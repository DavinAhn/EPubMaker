# -*- coding: utf-8 -*-

import sublime, sublime_plugin
import os
import shutil
import subprocess
import zipfile
import glob
import sys
import codecs
import json

###
### Global Value
###

PACKAGE_NAME		= 'EPubMaker'

OPEN_COMMAND		= 'epub_maker_open'
SAVE_COMMAND		= 'epub_maker_save'	

WORKSPACES_PATH = None

SUMMARY_EXTENSION		= 'sublime-epub-summary'
IDENTIFIER_EXTENSION	= 'sublime-epub-identifier'
PROJECT_EXTENSION		= 'sublime-project'

IGNORE_EXTENSIONS = [
	SUMMARY_EXTENSION, 
	IDENTIFIER_EXTENSION, 
	PROJECT_EXTENSION, 
	'sublime-workspace'
]

SETTINGS = {}

ST3 = sublime.version() >= '3000'

###
### EventListener
###

class EpubMakerEventListener(sublime_plugin.EventListener):
	def on_load(self, view):
		filename = view.file_name()
		if is_valid_format(filename, [SUMMARY_EXTENSION]): # summary 파일은 수정할 수 없도록
			view.set_read_only(True)
		elif not is_valid_format(filename): # epub 확장자 확인
			return
		elif ST3: # Sublime Text 3 확인
			global WORKSPACES_PATH
			if WORKSPACES_PATH is None: # workspaces 초기화 확인
				return
			else:
				view.run_command(OPEN_COMMAND) # epub 열기

	def on_post_save(self, view):
		if not get_setting('auto_save'):
			return
		view.run_command(SAVE_COMMAND) # epub 저장

###
### TextCommand
###

class EpubMakerOpenCommand(sublime_plugin.TextCommand):
	def is_enabled(self):
		return is_valid_format(self.view.file_name())

	def run(self, edit):
		def extract(workpath, namelist):
			os.makedirs(workpath)
			for name in namelist:
				filepath = os.path.join(workpath, name)
				dirname = os.path.dirname(filepath)
				if not os.path.exists(dirname): # 디렉토리가 존재하지 않는지
					os.makedirs(dirname)
				if os.path.isdir(filepath): # 디렉토리인지
					continue
				else:
					with open(filepath, 'wb') as descriptor:
						descriptor.write(epub.read(name))

		def close_views(workpath, namelist):
			activewindow = sublime.active_window()
			activeview = activewindow.active_view()
			for name in namelist:
				if name.startswith(workpath): # 절대경로 인지
					filepath = name
				else:
					filepath = os.path.join(workpath, name)
				for window in sublime.windows():
					for view in window.views():
						if view.file_name() == filepath:
							view.set_scratch(True)
							window.focus_view(view)
							window.run_command('close_file')
							break
			activewindow.focus_view(activeview)

		def close_folders(workpath):
			for window in sublime.windows():
				for folder in window.folders():
					if folder == workpath:
						window.run_command('remove_folder', {'dirs': [folder]})
						break
				window.run_command('refresh_folder_list')

		# 압축 해제
		epubpath = self.view.file_name()
		try:
			epub = zipfile.ZipFile(epubpath)
		except Exception as e:
			sublime.error_message('압축을 해제하는 중 오류가 발생했습니다')
			print(PACKAGE_NAME + ':open: \'' + epubpath + '\'의 압축을 해제하는 중 오류가 발생했습니다')
			return

		# workspace 생성
		global WORKSPACES_PATH
		workpath = os.path.join(WORKSPACES_PATH, os.path.splitext(os.path.basename(epubpath))[0])
		namelist = epub.namelist()
		close_views(workpath, namelist + [get_sumblime_project_path(workpath), get_epub_identifier_path(workpath), get_epub_summary_path(workpath)])
		close_folders(workpath)
		if not os.path.exists(workpath):
			extract(workpath, namelist)
		elif not sublime.ok_cancel_dialog('이전에 작업하던 ePub입니다.\n이어서 작업하시겠습니까?'):
			shutil.rmtree(workpath)
			extract(workpath, namelist)

		# 프로젝트 파일 생성
		idpath = create_epub_identifier(workpath, epubpath)
		projectpath = create_sublime_project(workpath)
		summarypath = create_epub_summary(workpath, epubpath)

		# epub 뷰 닫음
		view = self.view
		window = view.window()
		view.set_scratch(True)
		window.focus_view(view)
		window.run_command('close_file')

		# 생성된 프로젝트 오픈
		if is_windows():
			sumlpath = os.path.join(os.path.dirname(sublime.__file__), 'subl.exe')
		else:
			sumlpath = os.path.join(os.path.dirname(os.path.dirname(sublime.__file__)), 'SharedSupport', 'bin', 'subl')
		cmd = '"' + sumlpath + '" --project "' + projectpath + '" --add "' + summarypath + '"'
		if get_setting('new_window'):
			cmd += ' --new-window'
		subprocess.Popen(cmd, shell=True)
		window.run_command('refresh_folder_list')

		sublime.status_message('Opend ePub ' + epubpath)
		print(PACKAGE_NAME + ':open: \'' + epubpath + '\' -> \'' + workpath + '\'')

class EpubMakerSaveCommand(sublime_plugin.TextCommand):
	def run(self, edit):
		global WORKSPACES_PATH
		if not self.view.file_name().startswith(WORKSPACES_PATH): # epub과 관련된 파일이 아닐 때는 저장 무시
			return

		# epub-identifier 찾기
		filename = self.view.file_name()
		components = filename.replace(WORKSPACES_PATH, '').split(os.sep)
		if not len(components[0]) == 0:
			return
		workpath = os.path.join(WORKSPACES_PATH, components[1])
		if not os.path.exists(workpath):
			return
		if not os.path.isdir(workpath):
			return
		idpath = get_epub_identifier_path(workpath)
		if not os.path.exists(idpath):
			sublime.error_message('\'' + idpath + '\'를 찾을 수 없습니다')
			print(PACKAGE_NAME + ':save: \'' + idpath + '\'를 찾을 수 없습니다')
			return

		if get_setting('require_confirm_save'):
			if not sublime.ok_cancel_dialog('변경된 내용을 ePub에도 반영 하시겠습니까?'):
				return

		# epub-identifier 읽기
		idfile = open(idpath, 'r')
		epubid = json.loads(idfile.read())
		idfile.close()

		epubpath = None
		if get_setting('overwite_original'):
			epubpath = epubid['src_path']
			if not epubpath is None and get_setting('backup_original'):
				def backup(path):
					try:
						shutil.copy(path, path + '.' + get_setting('backup_extension'))
					except Exception as e:
						sublime.error_message('\'' + epubpath + '\'을 백업하는 중 오류가 발생했습니다')
						print(PACKAGE_NAME + ':save: \'' + epubpath + '\'을 백업하는 중 오류가 발생했습니다')
				backup(epubpath)
		if epubpath is None:
			epubpath = os.path.join(workpath, '..', os.path.basename(workpath)) + '.epub'

		epub = zipfile.ZipFile(epubpath, 'w')

		# ePub OCF에 따라 mimetype을 제일 먼저 압축없이 압축파일에 포함
		epub.writestr('mimetype', 'application/epub+zip', zipfile.ZIP_STORED)

		# 이후 디렉토리와 파일을 추가
		for root, dirs, files in os.walk(workpath):
			if root == workpath:
				continue
			epub.write(root, root[len(workpath + os.sep):], zipfile.ZIP_STORED)
			for f in files:
				if is_ignore_file(f) or f == 'mimetype':
					continue
				f = os.path.join(root, f)
				epub.write(f, f[len(workpath + os.sep):], zipfile.ZIP_DEFLATED)

		epub.close()

		sublime.status_message('Saved ePub ' + epubpath)
		print(PACKAGE_NAME + ':save: \'' + epubpath + '\'')

###
### Global Def (utility)
###

def set_extension(path=None, extension=None):
	if path is None or extension is None:
		return None
	else:
		return path + '.' + extension

def is_valid_format(filename=None, extensions=['epub']):
	if filename is None or '.' not in filename:
		return False
	else:
		return filename.rsplit('.', 1)[1] in extensions

def is_ignore_file(filename=None):
	if filename is None:
		return True
	elif is_valid_format(filename, IGNORE_EXTENSIONS):
		return True
	else:
		return False

def get_setting(key):
	return SETTINGS[key];

def load_settings():
	settings = sublime.load_settings(PACKAGE_NAME + '.sublime-settings')
	SETTINGS['new_window'] = settings.get('new_window', True)
	SETTINGS['auto_save'] = settings.get('auto_save', False)
	SETTINGS['require_confirm_save'] = settings.get('require_confirm_save', False)
	SETTINGS['overwite_original'] = settings.get('overwite_original', True)
	SETTINGS['backup_original'] = settings.get('backup_original', True)
	SETTINGS['backup_extension'] = settings.get('backup_extension', 'back')

# workpath: 할당된 작업 경로
def create_sublime_project(workpath):
	if not os.path.exists(workpath):
		return None
	else:
		projectpath = get_sumblime_project_path(workpath)
		with codecs.open(projectpath, 'w', 'utf-8') as project:
			project.write(json.dumps({"folders": [{"path": workpath}]}, sort_keys=True, indent=4, separators=(',', ': ')))
			project.close()
		return projectpath

def get_sumblime_project_path(workpath):
	return set_extension(os.path.join(workpath, os.path.basename(workpath)), PROJECT_EXTENSION)

# workpath: 할당된 작업 경로
# epubpath: 원본 ePub 파일의 경로
def create_epub_identifier(workpath, epubpath):
	if not os.path.exists(workpath):
		return None
	else:
		idpath = get_epub_identifier_path(workpath)
		with codecs.open(idpath, 'w', 'utf-8') as idf:
			idf.write(json.dumps({"src_path": epubpath, "work_path": workpath}, sort_keys=True, indent=4, separators=(',', ': ')))
			idf.close()
		return idpath

def get_epub_identifier_path(workpath):
	return set_extension(os.path.join(workpath, os.path.basename(workpath)), IDENTIFIER_EXTENSION)

# workpath: 할당된 작업 경로
# epubpath: 원본 ePub 파일의 경로
def create_epub_summary(workpath, epubpath):
	def size_of(filepath, suffix='B'):
		if not os.path.exists(filepath):
			size = 0
		elif os.path.isdir(filepath):
			size = 0
			for dirpath, dirnames, filenames in os.walk(filepath):
				for filename in filenames:
					size += os.path.getsize(os.path.join(dirpath, filename))
		else:
			size = os.path.getsize(filepath)
		for unit in ['','K','M','G']:
			if abs(size) < 1024.0:
				return '%3.1f%s%s' % (size, unit, suffix)
			size /= 1024.0
		return '%.1f%s' % (size, suffix)

	def list_files(startpath):
		tree = ''
		for root, dirs, files in os.walk(startpath):
			level = root.replace(startpath, '').count(os.sep)
			indent = ' ' * 4 * (level)
			tree += '{0}{1}{2}\n'.format(indent, os.path.basename(root), os.sep)
			subindent = ' ' * 4 * (level + 1)
			for f in files:
				if is_ignore_file(f):
					continue
				tree += '{0}{1} ({2})\n'.format(subindent, f, size_of(os.path.join(root, f)))
		return tree

	if not os.path.exists(workpath) or not os.path.exists(epubpath):
		return Non
	else:
		summarypath = get_epub_summary_path(workpath)
		with codecs.open(summarypath, 'w', 'utf-8') as summary:
			summary.write(os.path.basename(workpath) + '\n\n')
			summary.write('원본 경로: ' + epubpath + ' (' + size_of(epubpath) + ')\n')
			summary.write('작업 경로: ' + workpath + ' (' + size_of(workpath) + ')\n\n')
			summary.write('ePub 구조:\n')
			summary.write(list_files(workpath))
			summary.close()
		return summarypath

def get_epub_summary_path(workpath):
	return set_extension(os.path.join(workpath, os.path.basename(workpath)), SUMMARY_EXTENSION)

def get_platform_name():
	return sublime.platform()

def is_windows():
	return get_platform_name().startswith('windows')

def is_osx():
	return get_platform_name().startswith('osx')

###
### Global Def (setup)
###

def init_menu():
	menupath = os.path.join(sublime.packages_path(), PACKAGE_NAME, 'Main.sublime-menu')
	if os.path.exists(menupath):
		return
	else:
		with codecs.open(menupath, 'w', 'utf-8') as menu:
			menu.write(json.dumps([
				{
					"caption": "File",
					"mnemonic": "f",
					"id": "file",
					"children":
					[
						{
							"caption": "Save As ePub",
							"mnemonic": "e",
							"command": SAVE_COMMAND
						}
					]
				},
				{
					"caption": "Preferences",
					"mnemonic": "n",
					"id": "preferences",
					"children":
					[
						{
							"caption": "Package Settings",
							"mnemonic": "P",
							"id": "package-settings",
							"children":
							[
								{
									"caption": PACKAGE_NAME,
									"children":
									[
										{
											"command": "open_file",
											"args": {
												"file": "${packages}/" + PACKAGE_NAME + "/" + PACKAGE_NAME + ".sublime-settings"
											},
											"caption": "Settings – Default"
										},
										{
											"command": "open_file",
											"args": {
												"file": "${packages}/User/" + PACKAGE_NAME + ".sublime-settings"
											},
											"caption": "Settings – User"
										},
										{
											"caption": "-"
										}
									]
								}
							]
						}
					]
				}
			], sort_keys=True, indent=4, separators=(',', ': ')))
			menu.close()

def init_keymap():
	windowkeymappath = os.path.join(sublime.packages_path(), PACKAGE_NAME, 'Default (Windows).sublime-keymap')
	if os.path.exists(windowkeymappath):
		return
	else:
		with codecs.open(windowkeymappath, 'w', 'utf-8') as keymap:
			keymap.write(json.dumps([
				{"keys": ["shift+e"], "command": SAVE_COMMAND}
			], sort_keys=True, indent=4, separators=(',', ': ')))
			keymap.close()
	osxkeymappath = os.path.join(sublime.packages_path(), PACKAGE_NAME, 'Default (OSX).sublime-keymap')
	if os.path.exists(osxkeymappath):
		return
	else:
		with codecs.open(osxkeymappath, 'w', 'utf-8') as keymap:
			keymap.write(json.dumps([
				{"keys": ["super+shift+e"], "command": SAVE_COMMAND}
			], sort_keys=True, indent=4, separators=(',', ': ')))
			keymap.close()

def init_settings():
	load_settings()

def init_workspaces():
	global WORKSPACES_PATH
	if is_windows():
		WORKSPACES_PATH = os.path.join(os.getenv('HOMEDRIVE'), os.getenv('HOMEPATH'), 'Documents', PACKAGE_NAME, 'workspaces')
	else:
		WORKSPACES_PATH = os.path.join(os.getenv('HOME'), PACKAGE_NAME, 'workspaces')
	if not os.path.exists(WORKSPACES_PATH):
		os.makedirs(WORKSPACES_PATH)
	print(PACKAGE_NAME + ':init_workspaces: \'' + WORKSPACES_PATH + '\'')

def plugin_loaded():
	if not ST3:
		return
	if not is_windows and not is_osx:
		return
	init_menu()
	init_settings()
	init_workspaces()
