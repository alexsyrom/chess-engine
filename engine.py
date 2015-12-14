import sys
import threading
import cmd
import chess
import tables
from operator import attrgetter
from collections import deque

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


class Board(chess.Board):
    MIN_VALUE = tables.MIN_VALUE

    def _set_default_values(self):
        self.value_stack = deque((0,))
        self.number_stack = deque((32,))

    def __init__(self, *arg, **kwarg):
        super(Board, self).__init__(*arg, **kwarg)
        self._set_default_values()

    @property
    def value(self):
        return self.value_stack[-1]

    @property
    def number_of_pieces(self):
        return self.number_stack[-1]

    def _update_forward(self, move):
        number = self.number_of_pieces
        value = -self.value
        color = int(self.turn)
        phase_old = self.game_phase
        if self.piece_at(move.to_square):
            number -= 1
            value -= (
                tables.piece
                [phase_old]
                [self.piece_type_at(move.to_square)])
        self.number_stack.append(number)
        phase_new = self.game_phase
        piece_type_old = self.piece_type_at(move.from_square)
        value += (-1 + 2 * color) * (
            tables.piece_square
            [phase_old][color]
            [piece_type_old][move.from_square])
        if move.promotion:
            piece_type_new = move.promotion
            value += (-1 + 2 * color) * (
                tables.piece[phase_old][piece_type_old])
            value -= (-1 + 2 * color) * (
                tables.piece[phase_new][piece_type_new])
        else:
            piece_type_new = piece_type_old
        value -= (-1 + 2 * color) * (
            tables.piece_square
            [phase_new][color]
            [piece_type_new][move.to_square])
        self.value_stack.append(value)

    def _update_backward(self):
        self.value_stack.pop()
        self.number_stack.pop()

    def push(self, move):
        self._update_forward(move)
        super(Board, self).push(move)

    def pop(self):
        self._update_backward()
        return super(Board, self).pop()

    def reset(self):
        self._set_default_values()
        super(Board, self).reset()

    def set_fen(self, fen):
        super(Board, self).set_fen(fen)
        self.number_stack = deque((self._count_number_of_pieces(),))
        self.value_stack = deque((self._evaluate(),))

    def _count_number_of_pieces(self):
        number = 0
        for square in chess.SQUARES:
            if self.piece_at(square):
                number += 1
        return number

    def _evaluate_material(self, phase, color):
        value = 0
        for piece in chess.PIECE_TYPES:
            squares = self.pieces(piece, color)
            for square in squares:
                value += (tables.piece[phase][piece] +
                          tables.piece_square[phase][color][piece][square])
        return value

    def _evaluate(self):
        if self.is_checkmate():
            return self.MIN_VALUE
        if self.is_stalemate():
            return 0
        values = [0 for i in tables.PHASES]
        for phase in tables.PHASES:
            for color in map(int, chess.COLORS):
                values[phase] += (self._evaluate_material(phase, color) *
                                  (-1 + 2 * color))
        value = (values[0] * self.number_of_pieces +
                 values[1] * (32 - self.number_of_pieces)) // 32
        if self.turn == chess.BLACK:
            value *= -1
        return value

    @property
    def game_phase(self):
        if self.number_of_pieces > 16:
            return tables.OPENING
        else:
            return tables.ENGING


class Analyzer(threading.Thread):
    ALPHA = -tables.piece[tables.OPENING][chess.KNIGHT]
    BETA = -ALPHA

    def _set_default_values(self):
        self.infinite = False
        self.possible_first_moves = set()
        self.depth = 4
        self.number_of_nodes = 30

    def __init__(self, call_if_ready, call_to_inform):
        super(Analyzer, self).__init__()
        self.debug = False
        self._set_default_values()
        self.board = Board()

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

    def _generate_moves(self, current_depth):
        if current_depth == 0 and self.possible_first_moves:
            moves = [move for move in self.board.legal_moves
                     if move in self.possible_first_moves]
        else:
            moves = [move for move in self.board.legal_moves]
            # moves = self.board.legal_moves

        for move in moves:
            self.board.push(move)
            move.value = -self.board.value
            self.board.pop()
        moves.sort(key=attrgetter('value'), reverse=True)
        # moves = moves[:self.number_of_nodes]
        return moves

    def _inner_alpha_beta(self, current_depth, alpha, beta, moves):
        best_value = alpha
        if self.debug:
            self._call_to_inform('depth {}'.format(current_depth))
            self._call_to_inform(
                'string alpha {} beta {}'.format(alpha, beta))

        for move in moves:
            if self.debug:
                self._call_to_inform('currmove {}'.format(move.uci()))
            self.board.push(move)
            value = -self._alpha_beta(current_depth+1, -beta, -best_value)
            move.value = value
            if self.debug:
                self._call_to_inform('string value {}'.format(value))
            self.board.pop()

            if value >= beta:
                if current_depth == 0:
                    self._bestmove = move
                return value
            if value > best_value:
                best_value = value
                if current_depth == 0:
                    self._bestmove = move

        return best_value

    @Communicant()
    def _alpha_beta(self, current_depth, alpha, beta):
        if current_depth == self.depth or not self.is_working.is_set():
            return self.board.value
        if self.board.is_checkmate():
            return alpha
        if self.board.is_stalemate():
            return 0

        left_borders = [beta - (beta - alpha) // 2 ** i
                        for i in range(1, -1, -1)]
        moves = self._generate_moves(current_depth)
        if current_depth == 0 and moves:
            self._bestmove = moves[0]
        for left in left_borders:
            best_value = self._inner_alpha_beta(
                current_depth, left, beta, moves)
            if best_value > left:
                break
            moves.sort(key=attrgetter('value'), reverse=True)
        return best_value

    def run(self):
        while self.is_working.wait():
            if self.termination.is_set():
                sys.exit()
            self._bestmove = chess.Move.null()
            left = self.board.value + self.ALPHA
            right_borders = [self.board.value +
                             self.BETA * 2 ** i
                             for i in range(3)]
            for right in right_borders:
                value = self._alpha_beta(current_depth=0,
                                         alpha=left,
                                         beta=right)
                if value < right:
                    break
            self._call_to_inform('pv score cp {}'.format(value))
            self.is_working.clear()
            if not self.infinite:
                self._call_if_ready()
            self._set_default_values()


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
        print('bestmove', self.analyzer.bestmove.uci())

    def output_info(self, info_string):
        print('info', info_string)

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
            depth = min(depth, 4)
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
