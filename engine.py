# -*- coding: utf-8 -*-

import sys
import threading
import cmd
import chess

ENGINE_NAME = 'simple UCI chess engine'
AUTHOR_NAME = 'Alexey Syromyatnikov'


class Analyzer(threading.Thread):
    ALPHA = -1000 * 1000 * 1000
    BETA = 1000 * 1000 * 1000

    def set_default_values(self):
        self.infinite = False
        self.possible_first_moves = set()
        self.depth = 5
        self.number_of_nodes = 1000

    def __init__(self, call_if_ready, call_to_inform):
        super(Analyzer, self).__init__()
        self.debug = False
        self.set_default_values()
        self.board = chess.Board()

        self.is_working = threading.Event()
        self.is_working.clear()
        self.is_conscious = threading.Condition()
        self.termination = threading.Event()
        self.termination.clear()

        self._call_if_ready = call_if_ready
        self._call_to_inform = call_to_inform
        self._bestmove = chess.Move.null()

    @property
    def bestmove(self):
        return self._bestmove

    class Communicant():
        def __call__(self, func):
            def wrap(instance, *args, **kwargs):
                if instance.termination.is_set():
                    sys.exit()
                with instance.is_conscious:
                    instance.is_conscious.notify()
                result = func(instance, *args, **kwargs)
                with instance.is_conscious:
                    instance.is_conscious.notify()
                if instance.termination.is_set():
                    sys.exit()
                return result
            return wrap

    @Communicant()
    def evaluate(self):
        pass

    @Communicant()
    def alpha_beta(self, current_depth, alpha, beta):
        self._call_to_inform('wow')
        if current_depth == self.depth:
            return self.evaluate()

    def run(self):
        while self.is_working.wait():
            if self.termination.is_set():
                sys.exit()
            self.alpha_beta(current_depth=0, alpha=self.ALPHA, beta=self.BETA)
            self.is_working.clear()
            if not self.infinite:
                self._call_if_ready()
            self.set_default_values()


class EngineShell(cmd.Cmd):
    intro = ''
    prompt = ''
    file = None

    go_parameter_list = ['infinite', 'searchmoves', 'depth', 'nodes']

    def __init__(self):
        super(EngineShell, self).__init__()
        self.postinitialized = False

    def postinit(self):
        self.analyzer = Analyzer(self.output_bestmove, self.output_info)
        self.analyzer.start()
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
        arg = arg.split()
        if not arg:
            return
        if self.analyzer.is_working.is_set():
            '''
                something strange
                according to the protocol I should ignore it
                *if I ignore it, maybe it will go away*
            '''
            return
        if arg[0] == 'fen':
            self.analyzer.board.set_fen(' '.join(arg[1:]))
            arg.pop(0)
        else:
            if arg[0] == 'startpos':
                arg.pop(0)
            self.analyzer.board.reset()
        if arg[0] == 'moves':
            for move in arg[1:]:
                self.analyzer.board.push_uci(move)

    def do_go(self, arg):
        arg = arg.split()
        for parameter in self.go_parameter_list:
            try:
                index = arg.index(parameter)
            except:
                pass
            else:
                getattr(self, 'go_' + arg[index])(arg[index + 1:])
        try:
            index = arg.index('movetime')
            time = float(arg[index + 1])
        except:
            pass
        else:
            self.stop_timer = threading.Timer(time, self.do_stop)
        self.analyzer.is_working.set()

    def do_stop(self, arg=None):
        if hasattr(self, 'stop_timer'):
            self.stop_timer.cancel()
        if self.analyzer.is_working.is_set():
            self.analyzer.is_working.clear()
        else:
            self.output_bestmove()

    def do_quit(self, arg):
        self.analyzer.termination.set()
        self.analyzer.is_working.set()
        self.analyzer.join()
        sys.exit()

    def output_bestmove(self):
        print('bestmove', self.analyzer.bestmove.uci())

    def output_info(self, info_string):
        print('info string', info_string)

    def go_infinite(self, arg):
        self.analyzer.infinite = True

    def go_searchmoves(self, arg):
        self.analyzer.possible_first_moves = set()
        for uci_move in arg:
            try:
                move = chess.Move.from_uci(uci_move)
            except:
                break
            else:
                self.analyzer.possible_first_moves.add(move)

    def go_depth(self, arg):
        try:
            depth = int(arg[0])
        except:
            pass
        else:
            self.analyzer.depth = depth

    def go_nodes(self, arg):
        try:
            number_of_nodes = int(arg[0])
        except:
            pass
        else:
            self.analyzer.depth = number_of_nodes

    def default(self, arg):
        pass


if __name__ == '__main__':
    EngineShell().cmdloop()
