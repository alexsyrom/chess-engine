import sys
import threading
import cmd
import chess
import tables

ENGINE_NAME = 'simple UCI chess engine'
AUTHOR_NAME = 'Alexey Syromyatnikov'


class Unbuffered:
    def __init__(self, stream):
        self.stream = stream

    def write(self, data):
        self.stream.write(data)
        self.stream.flush()

    def __getattr__(self, attr):
        return getattr(self.stream, attr)

sys.stdout = Unbuffered(sys.stdout)


class Analyzer(threading.Thread):
    ALPHA = -1000 * 1000 * 1000
    BETA = 1000 * 1000 * 1000

    def set_default_values(self):
        self.infinite = False
        self.possible_first_moves = set()
        self.depth = 3
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

    class Communicant:
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

    def get_number_of_pieces(self):
        number = 0
        for square in chess.SQUARES:
            if self.board.piece_at(square):
                number += 1
        return number

    @Communicant()
    def evaluate_material(self, phase, color):
        value = 0
        for piece in chess.PIECE_TYPES:
            squares = self.board.pieces(piece, color)
            for square in squares:
                value += (tables.piece[phase][piece] +
                          tables.piece_square[phase][color][piece][square])
        return value

    @Communicant()
    def evaluate(self):
        values = [0 for i in tables.PHASES]
        for phase in tables.PHASES:
            for color in map(int, chess.COLORS):
                values[phase] += (self.evaluate_material(phase, color) *
                                  (-1 + 2 * color))
        number_of_pieces = self.get_number_of_pieces()
        value = (values[0] * number_of_pieces +
                 values[1] * (32 - number_of_pieces)) // 32
        if self.board.turn == chess.BLACK:
            value *= -1
        return value

    @Communicant()
    def alpha_beta(self, current_depth, alpha, beta):
        if current_depth == self.depth or not self.is_working.is_set():
            return self.evaluate()
        best_value = alpha
        moves = [move for move in self.board.legal_moves]
        moves = moves[:self.number_of_nodes]
        for move in moves:
            self.board.push(move)
            value = -self.alpha_beta(current_depth+1, -beta, -best_value)
            self.board.pop()
            if value >= beta:
                return beta
            if value > best_value:
                best_value = value
                if current_depth == 0:
                    self._bestmove = move
        return best_value

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
        if arg and arg[0] == 'moves':
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
        if hasattr(self, 'analyzer'):
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
