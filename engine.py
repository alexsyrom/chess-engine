# -*- coding: utf-8 -*-

import threading
import cmd

ENGINE_NAME = 'simple UCI chess engine'
AUTHOR_NAME = 'Alexey Syromyatnikov'


class Analyzer(threading.Thread):
    def __init__(self):
        super(Analyzer, self).__init__()
        self.debug = False

    def run(self):
        pass


class EngineShell(cmd.Cmd):
    intro = ''
    prompt = ''
    file = None

    def __init__(self):
        super(EngineShell, self).__init__()
        self.analyzer = Analyzer()

    def do_uci(self, arg):
        print('id name', ENGINE_NAME)
        print('id author', AUTHOR_NAME)
        print('uciok')

    def do_debug(self, arg):
        arg = arg.split()
        if arg:
            arg = arg[0]
        else:
            return
        if arg == 'on':
            self.analyzer.debug = True
        elif arg == 'off':
            self.analyzer.debug = False

    def do_isready(self, arg):
        pass

    def do_setoption(self, arg):
        pass

    def do_ucinewgame(self, arg):
        pass

    def do_position(self, arg):
        pass

    def do_stop(self, arg):
        pass

    def do_quit(self, arg):
        pass

    def default(self, arg):
        pass


if __name__ == '__main__':
    EngineShell().cmdloop()
