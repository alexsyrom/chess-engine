# -*- coding: utf-8 -*-

import threading
import cmd

ENGINE_NAME = 'simple UCI chess engine'
AUTHOR_NAME = 'Alexey Syromyatnikov'


class Analyzer(threading.Thread):
    def __init__(self):
        super(Analyzer, self).__init__()

    def run(self):
        pass


class EngineShell(cmd.Cmd):
    intro = ''
    prompt = ''
    file = None

    def do_uci(self, arg):
        print('id name', ENGINE_NAME)
        print('id author', AUTHOR_NAME)

    def default(self, arg):
        pass


if __name__ == '__main__':
    EngineShell().cmdloop()
