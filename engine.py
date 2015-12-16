import sys
import threading
import cmd
import chess
from chess import polyglot
import tables
import os

__location__ = os.path.realpath(
    os.path.join(os.getcwd(), os.path.dirname(__file__)))

logfile = open(os.path.join(__location__, 'input.log'), 'w')

ENGINE_NAME = 'simple UCI chess engine'
AUTHOR_NAME = 'Alexey Syromyatnikov'


class Analyzer(threading.Thread):
    MIN_VALUE = -10 * tables.piece[chess.KING]

    BETA = tables.piece[chess.ROOK]
    ALPHA = -BETA

    MAX_ITER = 2
    MULTIPLIER = 4

    MAX_NEGAMAX_ITER = 2
    NEGAMAX_DIVISOR = 3

    def set_default_values(self):
        self.infinite = False
        self.possible_first_moves = set()
        self.max_depth = 3
        self.number_of_nodes = 100

    def __init__(self, call_if_ready, call_to_inform, opening_book):
        super(Analyzer, self).__init__()
        if opening_book:
            self.opening_book = polyglot.open_reader(opening_book)
        else:
            self.opening_book = None
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

    @property
    def number_of_pieces(self):
        number = sum(1 for square in chess.SQUARES
                     if self.board.piece_at(square))
        return number

    def evaluate_material_position(self, phase, color, pieces):
        value = 0
        for piece in pieces:
            squares = self.board.pieces(piece, color)
            for square in squares:
                value += tables.piece_square[phase][color][piece][square]
        return value

    def evaluate_material(self, color):
        value = 0
        for piece in chess.PIECE_TYPES:
            squares = self.board.pieces(piece, color)
            value += len(squares) * tables.piece[piece]
        return value

    def evaluate(self):
        if self.board.is_checkmate():
            return self.MIN_VALUE
        if self.board.is_stalemate():
            return 0

        colors = list(map(int, chess.COLORS))

        values = [0 for i in tables.PHASES]
        phase = tables.OPENING
        pieces = list(range(1, 6))  # pieces without king
        for color in colors:
            values[phase] += (self.evaluate_material_position
                              (phase, color, pieces)
                              *
                              (-1 + 2 * color))
        values[tables.ENDING] = values[tables.OPENING]
        for phase in tables.PHASES:
            for color in colors:
                values[phase] += (self.evaluate_material_position
                                  (phase, color, (chess.KING,))
                                  *
                                  (-1 + 2 * color))

        material = [0 for i in colors]
        for color in colors:
            material[color] = self.evaluate_material(color)
        material_sum = sum(material)

        for color in colors:
            for phase in tables.PHASES:
                values[phase] += material[color] * (-1 + 2 * color)

        value = ((values[tables.OPENING] * material_sum +
                  values[tables.ENDING] * (tables.PIECE_SUM - material_sum))
                 // tables.PIECE_SUM)

        if self.board.turn == chess.BLACK:
            value *= -1

        return value

    def moves(self, depth):
        if depth == 0 and self.possible_first_moves:
            for move in self.board.legal_moves:
                if move in self.possible_first_moves:
                    yield move
        else:
            for move in self.board.legal_moves:
                yield move

    def inner_negamax(self, depth, alpha, beta):
        best_value = alpha

        for move in self.moves(depth):
            if self.debug:
                self._call_to_inform('currmove {}'.format(move.uci()))

            self.board.push(move)
            value = -self.negamax(depth+1, -beta, -best_value)

            if self.debug:
                self._call_to_inform('string value {}'.format(value))

            self.board.pop()

            if value >= beta:
                if depth == 0:
                    self._bestmove = move
                return beta
            elif value > best_value:
                best_value = value
                if depth == 0:
                    self._bestmove = move
            elif depth == 0 and not bool(self._bestmove):
                self._bestmove = move

        return best_value

    @Communicant()
    def negamax(self, depth, alpha, beta):
        if depth == self.max_depth or not self.is_working.is_set():
            return self.evaluate()

        if self.debug:
            self._call_to_inform('depth {}'.format(depth))
            self._call_to_inform('string alpha {} beta {}'.format(alpha, beta))

        value = alpha

        left_borders = [beta - (beta - alpha) // self.NEGAMAX_DIVISOR ** i
                        for i in range(self.MAX_NEGAMAX_ITER, -1, -1)]
        for left in left_borders:
            value = self.inner_negamax(depth, left, beta)
            if value > left:
                break

        return value

    def run(self):
        while self.is_working.wait():
            if self.termination.is_set():
                sys.exit()
            self._bestmove = chess.Move.null()

            try:
                if not self.possible_first_moves:
                    entry = self.opening_book.find(self.board)
                    self._bestmove = entry.move()
                else:
                    for entry in self.opening_book.find_all(self.board):
                        move = entry.move()
                        if move in self.possible_first_moves:
                            self._bestmove = move
                            break
            except:
                pass

            if not bool(self._bestmove):
                middle = self.evaluate()
                alpha = self.ALPHA
                beta = self.BETA
                for i in range(self.MAX_ITER):
                    value = self.negamax(depth=0,
                                         alpha=middle+alpha,
                                         beta=middle+beta)
                    if value >= middle + beta:
                        beta *= self.MULTIPLIER
                    elif value <= middle + alpha:
                        alpha *= self.MULTIPLIER
                    else:
                        break
                self._call_to_inform('pv score cp {}'.format(value))
            else:
                self._call_to_inform('string opening')
            self.is_working.clear()
            if not self.infinite:
                self._call_if_ready()
            self.set_default_values()


class EngineShell(cmd.Cmd):
    intro = ''
    prompt = ''
    file = None

    opening_book_list = ['gm2001',
                         'komodo',
                         'Human']
    opening_book = 'Human'
    opening_dir = 'opening'
    opening_book_extension = '.bin'

    go_parameter_list = ['infinite', 'searchmoves', 'depth', 'nodes']

    def __init__(self):
        super(EngineShell, self).__init__()
        self.postinitialized = False

    def postinit(self):
        opening_book = self.opening_book + self.opening_book_extension
        opening_book = os.path.join(self.opening_dir, opening_book)
        self.analyzer = Analyzer(
            self.output_bestmove,
            self.output_info,
            os.path.join(__location__, opening_book))
        self.analyzer.start()
        self.postinitialized = True

    def do_uci(self, arg):
        print('id name', ENGINE_NAME)
        print('id author', AUTHOR_NAME)
        print('option name OpeningBook type combo', end=' ')
        print('default', self.opening_book, end=' ')
        for book in self.opening_book_list:
            print('var', book, end=' ')
        print()
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
        arg = arg.split()
        try:
            if arg[0] != 'name':
                return
            arg.pop(0)
            if (arg[0] == 'OpeningBook' and
                    arg[1] == 'value' and
                    arg[2] in self.opening_book_list):
                self.opening_book = arg[2]
        except:
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
        if arg[0] == 'fen' and len(arg) >= 7:
            self.analyzer.board.set_fen(' '.join(arg[1:7]))
            del arg[:7]
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
        print('bestmove', self.analyzer.bestmove.uci(),
              file=self.stdout, flush=True)

    def output_info(self, info_string):
        print('info', info_string,
              file=self.stdout, flush=True)

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
        if not self.analyzer.debug:
            return
        try:
            depth = int(arg[0])
        except:
            pass
        else:
            self.analyzer.max_depth = depth

    def go_nodes(self, arg):
        try:
            number_of_nodes = int(arg[0])
        except:
            pass
        else:
            self.analyzer.depth = number_of_nodes

    def default(self, arg):
        pass

    def precmd(self, line):
        print(line, file=logfile, flush=True)
        return line

    def postcmd(self, stop, line):
        self.stdout.flush()
        return stop


if __name__ == '__main__':
    print('new start', file=logfile, flush=True)
    EngineShell().cmdloop()
