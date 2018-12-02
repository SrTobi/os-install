#!/usr/bin/python3
import json
import os
import sys
import tempfile
import subprocess
import re
from os import path
from argparse import ArgumentParser
from collections import defaultdict

# process arguments
def load_args():
    parser = ArgumentParser(description='Install os', prog='os-install')
    parser.add_argument('script', help='The install script')
    parser.add_argument('--new', action='store_true')
    parser.add_argument('--overwrite', action='store_true')
    parser.add_argument('--pp', action='store_true')
    return parser.parse_args()

# load db
class Db:
    def __init__(self, filename, data):
        self.filename = filename
        self.data = data
    
    def new(filename):
        return Db(filename, { "executed": {}, "vars": {}})

    def load(filename):
        with open(filename) as f:
            data = json.load(f)
        return Db(filename, data)
    
    def save(self):
        with open(self.filename, "w+") as f:
            json.dump(self.data, f, indent=2)
    
    def was_executed(self, name):
        return name in self.data['executed']
    
    def mark_executed(self, name):
        self.data["executed"][name] = True
        self.save()
    
    def get_var(self, name):
        if name in self.data['vars']:
            return self.data['vars'][name]
        return None
    
    def set_var(self, name, value):
        self.data['vars'][name] = value
        self.save()
    


############# Start #############
pargs = load_args()

# Init DB
script_path, script_filename = path.split(pargs.script)
config_filepath = path.join(script_path, 'config-%s.json' % script_filename)

print('Scriptfile: ' + pargs.script)
print('Config filepath: ' + config_filepath)

if pargs.new:
    if path.exists(config_filepath) and not pargs.overwrite:
        sys.exit('Config file "%s" already exists! Delete it to start new install.' % config_filepath)
    db = Db.new(config_filepath)
else:
    if not path.exists(config_filepath):
        sys.exit('Config file "%s" does not exist' % config_filepath)
    db = Db.load(config_filepath)

# Load script pieces
class PieceInput:
    def __init__(self, name, desc):
        self.name = name
        self.desc = desc

    def resolve(self):
        value = db.get_var(self.name)
        if value is None:
            value = input('> %s: ' % self.desc)
            db.set_var(self.name, value)
        return value


class ScriptPiece:
    def __init__(self, name, lines, imports):
        self.name = name
        self.lines = lines
        self.imports = imports
    
    def __repr__(self):
        return 'ScriptPiece(%s)' % self.name
    
    def execute(self):
        if db.was_executed(self.name):
            print('>>> "%s" was already executed' % self.name)
            return
        print('>>> Execute: %s' % self.name)

        lines = ['%s=%s' % (v.name, v.resolve()) for v in self.imports] + self.lines
        fd, path = tempfile.mkstemp()
        def print_lines():
            print('!!!!!!!!!!!!!!!!!!!!!!!')
            for line in lines:
                print('!! %s' % line)
            print('!!!!!!!!!!!!!!!!!!!!!!!')
        

        with os.fdopen(fd, 'w') as tmp:
            for line in lines:
                tmp.write(line + '\n')
        
        if pargs.pp:
            print_lines()

        if subprocess.call(['bash', path]):
            if not pargs.pp:
                print_lines()
            sys.exit('"%s" in "%s" failed!' % (self.name, path))
        else:
            db.mark_executed(self.name)
        
        os.remove(path)


def group_script_pieces(filename):
    with open(filename) as f:
        all_vars = {}
        imported_vars = []
        prolog = []
        lines = []
        curname = ''
            
        for line in f:
            line = line.strip()
            m = re.match(r'\s*#\s*var\s+(\w+)\s*:(.+)', line)
            m2 = re.match(r'\s*#\s*import\s+(\w+)$', line)
            if line.startswith('##'):
                if curname.lower() == 'prolog':
                    if prolog:
                        sys.exit('Can not have mulitple prologs')
                    prolog = lines
                elif lines and curname:
                    yield ScriptPiece(curname, prolog + lines, imported_vars)
                curname = line[3:]
                lines = []
                imported_vars = []
            elif m:
                name, desc = m.group(1, 2)
                if name in all_vars:
                    sys.exit('Var "%s" already defined' % name)
                v = PieceInput(name, desc.strip())
                all_vars[name] = v
                imported_vars.append(v)
            elif m2:
                name = m2.group(1)
                if name not in all_vars:
                    sys.exit('Can not import "%s" because it is not defined' % name)
                imported_vars.append(all_vars[name])
            lines.append(line)

        if lines and curname:
            yield ScriptPiece(curname, prolog + lines, imported_vars)

pieces = list(group_script_pieces(pargs.script))

# Check if multiple script pieces have the same name
def check_for_duplicates():
    found = set()
    for piece in pieces:
        if piece.name in found:
            sys.exit('Script piece "%s" exists twice' % piece.name)
        found.add(piece.name)

check_for_duplicates()


# Execute pieces
print()
print('Start executing...')
for piece in pieces:
    piece.execute()