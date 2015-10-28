# -*- coding: utf-8 -*-

import sublime, sublime_plugin
import os
import platform
import shutil
import zipfile
import glob
import sys
import codecs
import json

###
### Global Value
###

WORKSPACES_PATH = None

SUMMARY_EXTENSION		= 'epub-summary'
IDENTIFIER_EXTENSION	= 'epub-identifier'
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
		if not is_valid_format(view.file_name()):
			return
		elif ST3:
			global WORKSPACES_PATH
			if WORKSPACES_PATH is None:
				return
			else:
				view.run_command('epub_maker_open')

	def on_post_save(self, view):
		if get_setting('auto_save') == False:
			return
		if get_setting('require_confirm_save'):
			if not sublime.ok_cancel_dialog('변경된 내용을 ePub 파일에도 반영 하시겠습니까?'):
				return
		view.run_command('epub_maker_save')

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
				if not os.path.exists(dirname):
					os.makedirs(dirname)
					if os.path.isdir(filepath):
						continue
					else:
						with open(filepath, 'wb') as descriptor:
							descriptor.write(epub.read(name))

		epubpath = self.view.file_name()
		try:
			epub = zipfile.ZipFile(epubpath)
		except Exception as e:
			print('EPubMaker:open: \'' + epubpath + '\'의 압축을 해제하는 중 오류가 발생했습니다')
			return
		global WORKSPACES_PATH
		workpath = os.path.join(WORKSPACES_PATH, os.path.splitext(os.path.basename(epubpath))[0])
		namelist = epub.namelist()
		if not os.path.exists(workpath):
			extract(workpath, namelist)
		elif not sublime.ok_cancel_dialog('이전에 작업하던 파일입니다.\n이어서 작업하시겠습니까?'):
			shutil.rmtree(workpath)
			extract(workpath, namelist)
		window = self.view.window()
		create_sublime_project(workpath)
		create_epub_identifier(workpath, epubpath)
		summarypath = create_epub_summary(workpath, epubpath)
		self.view.set_scratch(True)
		window.focus_view(self.view)
		window.run_command('close_file')
		window.run_command('open_file', {'file': summarypath})
		print('EPubMaker:open: \'' + epubpath + '\' -> \'' + workpath + '\'')
		sublime.status_message('Opend ePub ' + epubpath)
		sublime.set_timeout(load_side_bar(summarypath), 100)

class EpubMakerSaveCommand(sublime_plugin.TextCommand):
	pass

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
    settings = sublime.load_settings('EPubMaker.sublime-settings')
    SETTINGS['auto_save'] = settings.get('auto_save', False)
    SETTINGS['require_confirm_save'] = settings.get('require_confirm_save', False)
    SETTINGS['overwite_original'] = settings.get('overwite_original', False)

def load_side_bar(summarypath):
	for window in sublime.windows():
		for view in window.views():
			if view.file_name() == summarypath:
				window.focus_view(view)
				view.run_command('side_bar_new_directory')
				return
	sublime.set_timeout(load_side_bar(summarypath), 100)

# workpath: 할당된 작업 경로
def create_sublime_project(workpath):
	if not os.path.exists(workpath):
		return None
	else:
		projectpath = set_extension(os.path.join(workpath, os.path.basename(workpath)), PROJECT_EXTENSION)
		with codecs.open(projectpath, 'w', 'utf-8') as project:
			project.write('{\n\t\"folders\":\n\t[\n\t\t{\n\t\t\t\"path\": \"' + workpath + '\"\n\t\t}\n\t]\n}')
			project.close()
		return projectpath

# workpath: 할당된 작업 경로
# epubpath: 원본 ePub 파일의 경로
def create_epub_identifier(workpath, epubpath):
	if not os.path.exists(workpath):
		return None
	else:
		idpath = set_extension(os.path.join(workpath, os.path.basename(workpath)), IDENTIFIER_EXTENSION)
		with codecs.open(idpath, 'w', 'utf-8') as idf:
			idf.write('{\n\t\"src_path\": \"' + epubpath + '\",\n\t\"work_path\": \"' + workpath + '\"\n}')
			idf.close()
		return idpath

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
		summarypath = set_extension(os.path.join(workpath, os.path.basename(workpath)), SUMMARY_EXTENSION)
		with codecs.open(summarypath, 'w', 'utf-8') as summary:
			summary.write(os.path.basename(workpath) + '\n\n')
			summary.write('원본 경로: ' + epubpath + ' (' + size_of(epubpath) + ')\n')
			summary.write('작업 경로: ' + workpath + ' (' + size_of(workpath) + ')\n\n')
			summary.write('ePub 구조:\n')
			summary.write(list_files(workpath))
			summary.close()
		return summarypath

###
### Global Def (setup)
###

def init_menu():
	pass

def init_keymap():
	pass

def init_settings():
	load_settings()

def init_workspaces():
	global WORKSPACES_PATH
	if platform.platform().startswith('Windows'):
		WORKSPACES_PATH = os.path.join(os.getenv('HOMEDRIVE'), os.getenv('HOMEPATH'), 'EPubMaker', 'workspaces')
	else:
		WORKSPACES_PATH = os.path.join(os.getenv('HOME'), 'EPubMaker', 'workspaces')
	if not os.path.exists(WORKSPACES_PATH):
		os.makedirs(WORKSPACES_PATH)
	print('EPubMaker:init_workspaces: \'' + WORKSPACES_PATH + '\'')

def plugin_loaded():
	init_menu()
	init_keymap()
	init_settings()
	init_workspaces()
