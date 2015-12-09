# -*- coding: utf-8 -*-

import threading
import cmd
import chess

ENGINE_NAME = 'simple UCI chess engine'
AUTHOR_NAME = 'Alexey Syromyatnikov'


class Analyzer(threading.Thread):
    def __init__(self):
        super(Analyzer, self).__init__()
        self.debug = False
        self.is_working = threading.Event()
        self.is_working.clear()
        self.is_conscious = threading.Condition()
        self.is_bestmove_ready = threading.Event()
        self.is_bestmove_ready.clear()

        self._bestmove = chess.Move.null()

    @property
    def bestmove(self):
        return self._bestmove.uci()

    def run(self):
        pass


class EngineShell(cmd.Cmd):
    intro = ''
    prompt = ''
    file = None

    def __init__(self):
        super(EngineShell, self).__init__()
        self.postinitialized = False

    def postinit(self):
        self.analyzer = Analyzer()
        self.postinitialized = True

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
        if not self.postinitialized:
            self.postinit()
        if self.analyzer.is_working.is_set():
            with self.analyzer.is_conscious:
                self.analyzer.is_conscious.wait()
        print('readyok')

    def do_setoption(self, arg):
        pass

    def do_ucinewgame(self, arg):
        pass

    def do_position(self, arg):
        pass

    def do_go(self, arg):
        pass

    def do_stop(self, arg):
        if self.analyzer.is_working.is_set():
            self.analyzer.is_working.clear()
            with self.analyzer.is_bestmove_ready:
                self.analyzer.is_bestmove_ready.wait()
        print(self.analyzer.bestmove)

    def do_quit(self, arg):
        pass

    def default(self, arg):
        pass


if __name__ == '__main__':
    EngineShell().cmdloop()
