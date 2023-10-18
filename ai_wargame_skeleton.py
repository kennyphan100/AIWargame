from __future__ import annotations
import argparse
import copy
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field
from time import sleep
from typing import Tuple, TypeVar, Type, Iterable, ClassVar
import random
import requests
import os

# maximum and minimum values for our heuristic scores (usually represents an end of game condition)
MAX_HEURISTIC_SCORE = 2000000000
MIN_HEURISTIC_SCORE = -2000000000

map = {}
nb_of_leaf_nodes = 0

class UnitType(Enum):
    """Every unit type."""
    AI = 0
    Tech = 1
    Virus = 2
    Program = 3
    Firewall = 4

class Player(Enum):
    """The 2 players."""
    Attacker = 0
    Defender = 1

    def next(self) -> Player:
        """The next (other) player."""
        if self is Player.Attacker:
            return Player.Defender
        else:
            return Player.Attacker

class GameType(Enum):
    AttackerVsDefender = 0
    AttackerVsComp = 1
    CompVsDefender = 2
    CompVsComp = 3

##############################################################################################################

@dataclass(slots=True)
class Unit:
    player: Player = Player.Attacker
    type: UnitType = UnitType.Program
    health : int = 9
    # class variable: damage table for units (based on the unit type constants in order)
    damage_table : ClassVar[list[list[int]]] = [
        [3,3,3,3,1], # AI
        [1,1,6,1,1], # Tech
        [9,6,1,6,1], # Virus
        [3,3,3,3,1], # Program
        [1,1,1,1,1], # Firewall
    ]
    # class variable: repair table for units (based on the unit type constants in order)
    repair_table : ClassVar[list[list[int]]] = [
        [0,1,1,0,0], # AI
        [3,0,0,3,3], # Tech
        [0,0,0,0,0], # Virus
        [0,0,0,0,0], # Program
        [0,0,0,0,0], # Firewall
    ]

    def is_alive(self) -> bool:
        """Are we alive ?"""
        return self.health > 0

    def mod_health(self, health_delta : int):
        """Modify this unit's health by delta amount."""
        self.health += health_delta
        if self.health < 0:
            self.health = 0
        elif self.health > 9:
            self.health = 9

    def to_string(self) -> str:
        """Text representation of this unit."""
        p = self.player.name.lower()[0]
        t = self.type.name.upper()[0]
        return f"{p}{t}{self.health}"
    
    def __str__(self) -> str:
        """Text representation of this unit."""
        return self.to_string()
    
    def damage_amount(self, target: Unit) -> int:
        """How much can this unit damage another unit."""
        amount = self.damage_table[self.type.value][target.type.value]
        if target.health - amount < 0:
            return target.health
        return amount

    def repair_amount(self, target: Unit) -> int:
        """How much can this unit repair another unit."""
        amount = self.repair_table[self.type.value][target.type.value]
        if target.health + amount > 9:
            return 9 - target.health
        return amount

##############################################################################################################

@dataclass(slots=True)
class Coord:
    """Representation of a game cell coordinate (row, col)."""
    row : int = 0
    col : int = 0

    def col_string(self) -> str:
        """Text representation of this Coord's column."""
        coord_char = '?'
        if self.col < 16:
                coord_char = "0123456789abcdef"[self.col]
        return str(coord_char)

    def row_string(self) -> str:
        """Text representation of this Coord's row."""
        coord_char = '?'
        if self.row < 26:
                coord_char = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[self.row]
        return str(coord_char)

    def to_string(self) -> str:
        """Text representation of this Coord."""
        return self.row_string()+self.col_string()
    
    def __str__(self) -> str:
        """Text representation of this Coord."""
        return self.to_string()
    
    def clone(self) -> Coord:
        """Clone a Coord."""
        return copy.copy(self)

    def iter_range(self, dist: int) -> Iterable[Coord]:
        """Iterates over Coords inside a rectangle centered on our Coord."""
        for row in range(self.row-dist,self.row+1+dist):
            for col in range(self.col-dist,self.col+1+dist):
                yield Coord(row,col)

    def iter_adjacent(self) -> Iterable[Coord]:
        """Iterates over adjacent Coords."""
        yield Coord(self.row-1,self.col)
        yield Coord(self.row,self.col-1)
        yield Coord(self.row+1,self.col)
        yield Coord(self.row,self.col+1)

    @classmethod
    def from_string(cls, s : str) -> Coord | None:
        """Create a Coord from a string. ex: D2."""
        s = s.strip()
        for sep in " ,.:;-_":
                s = s.replace(sep, "")
        if (len(s) == 2):
            coord = Coord()
            coord.row = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".find(s[0:1].upper())
            coord.col = "0123456789abcdef".find(s[1:2].lower())
            return coord
        else:
            return None

##############################################################################################################

@dataclass(slots=True)
class CoordPair:
    """Representation of a game move or a rectangular area via 2 Coords."""
    src : Coord = field(default_factory=Coord)
    dst : Coord = field(default_factory=Coord)

    def to_string(self) -> str:
        """Text representation of a CoordPair."""
        return self.src.to_string()+" "+self.dst.to_string()
    
    def __str__(self) -> str:
        """Text representation of a CoordPair."""
        return self.to_string()

    def clone(self) -> CoordPair:
        """Clones a CoordPair."""
        return copy.copy(self)

    def iter_rectangle(self) -> Iterable[Coord]:
        """Iterates over cells of a rectangular area."""
        for row in range(self.src.row,self.dst.row+1):
            for col in range(self.src.col,self.dst.col+1):
                yield Coord(row,col)

    @classmethod
    def from_quad(cls, row0: int, col0: int, row1: int, col1: int) -> CoordPair:
        """Create a CoordPair from 4 integers."""
        return CoordPair(Coord(row0,col0),Coord(row1,col1))
    
    @classmethod
    def from_dim(cls, dim: int) -> CoordPair:
        """Create a CoordPair based on a dim-sized rectangle."""
        return CoordPair(Coord(0,0),Coord(dim-1,dim-1))
    
    @classmethod
    def from_string(cls, s : str) -> CoordPair | None:
        """Create a CoordPair from a string. ex: A3 B2"""
        s = s.strip()
        for sep in " ,.:;-_":
                s = s.replace(sep, "")
        if (len(s) == 4):
            coords = CoordPair()
            coords.src.row = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".find(s[0:1].upper())
            coords.src.col = "0123456789abcdef".find(s[1:2].lower())
            coords.dst.row = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".find(s[2:3].upper())
            coords.dst.col = "0123456789abcdef".find(s[3:4].lower())
            return coords
        else:
            return None

##############################################################################################################

@dataclass(slots=True)
class Options:
    """Representation of the game options."""
    dim: int = 5
    max_depth : int | None = 4
    min_depth : int | None = 2
    max_time : float | None = 5.0
    game_type : GameType = GameType.AttackerVsDefender
    alpha_beta : bool = True
    max_turns : int | None = 100
    randomize_moves : bool = True
    broker : str | None = None
    heuristic : str | None = "e0"
                
##############################################################################################################

@dataclass(slots=True)
class Stats:
    """Representation of the global game statistics."""
    evaluations_per_depth : dict[int,int] = field(default_factory=dict)
    total_seconds: float = 0.0

##############################################################################################################

@dataclass(slots=True)
class Game:
    """Representation of the game state."""
    board: list[list[Unit | None]] = field(default_factory=list)
    next_player: Player = Player.Attacker
    turns_played : int = 0
    options: Options = field(default_factory=Options)
    stats: Stats = field(default_factory=Stats)
    _attacker_has_ai : bool = True
    _defender_has_ai : bool = True

    def __post_init__(self):
        """Automatically called after class init to set up the default board state."""
        dim = self.options.dim
        self.board = [[None for _ in range(dim)] for _ in range(dim)]
        md = dim-1
        self.set(Coord(0,0),Unit(player=Player.Defender,type=UnitType.AI))
        self.set(Coord(1,0),Unit(player=Player.Defender,type=UnitType.Tech))
        self.set(Coord(0,1),Unit(player=Player.Defender,type=UnitType.Tech))
        self.set(Coord(2,0),Unit(player=Player.Defender,type=UnitType.Firewall))
        self.set(Coord(0,2),Unit(player=Player.Defender,type=UnitType.Firewall))
        self.set(Coord(1,1),Unit(player=Player.Defender,type=UnitType.Program))
        self.set(Coord(md,md),Unit(player=Player.Attacker,type=UnitType.AI))
        self.set(Coord(md-1,md),Unit(player=Player.Attacker,type=UnitType.Virus))
        self.set(Coord(md,md-1),Unit(player=Player.Attacker,type=UnitType.Virus))
        self.set(Coord(md-2,md),Unit(player=Player.Attacker,type=UnitType.Program))
        self.set(Coord(md,md-2),Unit(player=Player.Attacker,type=UnitType.Program))
        self.set(Coord(md-1,md-1),Unit(player=Player.Attacker,type=UnitType.Firewall))

    def clone(self) -> Game:
        """Make a new copy of a game for minimax recursion.

        Shallow copy of everything except the board (options and stats are shared).
        """
        new = copy.copy(self)
        new.board = copy.deepcopy(self.board)
        return new

    def is_empty(self, coord : Coord) -> bool:
        """Check if contents of a board cell of the game at Coord is empty (must be valid coord)."""
        return self.board[coord.row][coord.col] is None

    def get(self, coord : Coord) -> Unit | None:
        """Get contents of a board cell of the game at Coord."""
        if self.is_valid_coord(coord):
            return self.board[coord.row][coord.col]
        else:
            return None

    def set(self, coord : Coord, unit : Unit | None):
        """Set contents of a board cell of the game at Coord."""
        if self.is_valid_coord(coord):
            self.board[coord.row][coord.col] = unit

    def remove_dead(self, coord: Coord):
        """Remove unit at Coord if dead."""
        unit = self.get(coord)
        if unit is not None and not unit.is_alive():
            self.set(coord,None)
            if unit.type == UnitType.AI:
                if unit.player == Player.Attacker:
                    self._attacker_has_ai = False
                else:
                    self._defender_has_ai = False

    def mod_health(self, coord : Coord, health_delta : int):
        """Modify health of unit at Coord (positive or negative delta)."""
        target = self.get(coord)
        if target is not None:
            target.mod_health(health_delta)
            self.remove_dead(coord)

    def is_engaged_in_combat(self, coord : Coord) -> bool:
        for adj_unit in coord.iter_adjacent():
            if self.is_valid_coord(adj_unit) and self.get(adj_unit) and self.get(adj_unit).player != self.get(coord).player:
                return True
        return False

    def is_move_down(self, coords : CoordPair) -> bool:
        return ([coords.src.row+1, coords.src.col] == [coords.dst.row, coords.dst.col])
    
    def is_move_right(self, coords : CoordPair) -> bool:
        return ([coords.src.row, coords.src.col+1] == [coords.dst.row, coords.dst.col])
    
    def is_move_up(self, coords : CoordPair) -> bool:
        return ([coords.src.row-1, coords.src.col] == [coords.dst.row, coords.dst.col])
    
    def is_move_left(self, coords : CoordPair) -> bool:
        return ([coords.src.row, coords.src.col-1] == [coords.dst.row, coords.dst.col])

    def is_valid_move(self, coords : CoordPair) -> bool:
        """Validate a move expressed as a CoordPair. TODO: WRITE MISSING CODE!!!"""
        if not self.is_valid_coord(coords.src) or not self.is_valid_coord(coords.dst):
            return False
        
        unit = self.get(coords.src)
        if unit is None or unit.player != self.next_player:
            return False
        
        # === RETURN FALSE IF THE DESTINATION COORDINATE IS NOT ADJACENT TO SOURCE COORDINATE ===
        if (not self.is_adjacent(coords.src, coords.dst)):
            return False

        # === RETURN FALSE IF THE UNIT (AI, Firewall or Program) IS ENGAGED IN COMBAT ===
        if (unit.type == UnitType.AI or unit.type == UnitType.Firewall or unit.type == UnitType.Program) and self.is_engaged_in_combat(coords.src):
            return False
   
        # === RETURN FALSE FOR MOVE DOWN OR MOVE RIGHT FOR THE ATTACKER'S AI, Firewall, and Program ===
        if unit.player == Player.Attacker and (unit.type == UnitType.AI or unit.type == UnitType.Firewall or unit.type == UnitType.Program) and (self.is_move_down(coords) or self.is_move_right(coords)):
            return False
        
        # === RETURN FALSE FOR MOVE UP OR MOVE LEFT FOR THE DEFENDER'S AI, Firewall, and Program ===
        if unit.player == Player.Defender and (unit.type == UnitType.AI or unit.type == UnitType.Firewall or unit.type == UnitType.Program) and (self.is_move_up(coords) or self.is_move_left(coords)):
            return False
        
        unit = self.get(coords.dst)
        return (unit is None)

    def perform_move(self, coords : CoordPair) -> Tuple[bool,str]:
        """Validate and perform a move expressed as a CoordPair. TODO: WRITE MISSING CODE!!!"""
        if self.is_valid_move(coords):
            self.set(coords.dst,self.get(coords.src))
            self.set(coords.src,None)
            return (True,"move")
        if self.is_valid_to_attack(coords):
            self.attack(coords)
            return (True, "attack")
        if self.is_valid_to_repair(coords):
            self.repair(coords)
            return (True, "repair")
        if self.is_valid_to_self_destruct(coords):
            self.self_destruct(coords)
            return(True, "self-destruct")
        return (False,"invalid move")

    def next_turn(self):
        """Transitions game to the next turn."""
        self.next_player = self.next_player.next()
        self.turns_played += 1

    def to_string(self) -> str:
        """Pretty text representation of the game."""
        dim = self.options.dim
        output = ""
        output += f"Next player: {self.next_player.name}\n"
        output += f"Turns played: {self.turns_played}\n"
        coord = Coord()
        output += "\n   "
        for col in range(dim):
            coord.col = col
            label = coord.col_string()
            output += f"{label:^3} "
        output += "\n"
        for row in range(dim):
            coord.row = row
            label = coord.row_string()
            output += f"{label}: "
            for col in range(dim):
                coord.col = col
                unit = self.get(coord)
                if unit is None:
                    output += " .  "
                else:
                    output += f"{str(unit):^3} "
            output += "\n"
        return output

    def __str__(self) -> str:
        """Default string representation of a game."""
        return self.to_string()
    
    def is_valid_coord(self, coord: Coord) -> bool:
        """Check if a Coord is valid within out board dimensions."""
        dim = self.options.dim
        if coord.row < 0 or coord.row >= dim or coord.col < 0 or coord.col >= dim:
            return False
        return True

    def read_move(self) -> CoordPair:
        """Read a move from keyboard and return as a CoordPair."""
        while True:
            s = input(F'Player {self.next_player.name}, enter your move (enter q to quit): ')
            if (s == 'q'):
                print("Exiting game.")
                exit()
            coords = CoordPair.from_string(s)
            if coords is not None and self.is_valid_coord(coords.src) and self.is_valid_coord(coords.dst):
                return coords
            else:
                print('Invalid coordinates! Try again.')
    
    def human_turn(self) -> str:
        """Human player plays a move (or get via broker)."""
        if self.options.broker is not None:
            print("Getting next move with auto-retry from game broker...")
            while True:
                mv = self.get_move_from_broker()
                if mv is not None:
                    (success,result) = self.perform_move(mv)
                    print(f"Broker {self.next_player.name}: ",end='')
                    print(result)
                    if success:
                        self.next_turn()
                        break
                sleep(0.1)
        else:
            while True:
                mv = self.read_move()
                (success,result) = self.perform_move(mv)
                if success:
                    print(f"Player {self.next_player.name}: ",end='')
                    print(result)
                    if result == "attack":
                        self.next_turn()
                        return " attacks from " + mv.src.to_string() + " to " + mv.dst.to_string() + "."
                    if result == "repair":
                        self.next_turn()
                        return " repairs from " + mv.src.to_string() + " to " + mv.dst.to_string() + "."
                    if result == "self-destruct":
                        self.next_turn()
                        return " self-destructs from " + mv.src.to_string() + " to " + mv.dst.to_string() + "."
                    if result == "move":
                        self.next_turn()
                        return " moves from " + mv.src.to_string() + " to " + mv.dst.to_string() + "."
                else:
                    print("The move is not valid! Try again.")
                    return " move from " + mv.src.to_string() + " to " + mv.dst.to_string() + ". The move is not valid! Try again."

    def computer_turn(self, fileName) -> CoordPair | None:
        """Computer plays a move."""
        mv = self.suggest_move(fileName)
        if mv is not None:
            (success,result) = self.perform_move(mv)
            if success:
                outputFile = open(fileName, "a")
                print(f"Computer {self.next_player.name}: {result} from {mv.src.to_string()} to {mv.dst.to_string()}\n",end='')
                outputFile.write(f"Computer {self.next_player.name}: {result} from {mv.src.to_string()} to {mv.dst.to_string()}\n\n")
                outputFile.close()
                self.next_turn()
        else:
            return None
        return mv

    def player_units(self, player: Player) -> Iterable[Tuple[Coord,Unit]]:
        """Iterates over all units belonging to a player."""
        for coord in CoordPair.from_dim(self.options.dim).iter_rectangle():
            unit = self.get(coord)
            if unit is not None and unit.player == player:
                yield (coord,unit)

    def is_finished(self) -> bool:
        """Check if the game is over."""
        return self.has_winner() is not None

    def has_winner(self) -> Player | None:
        """Check if the game is over and returns winner"""
        if self.options.max_turns is not None and self.turns_played >= self.options.max_turns:
            return Player.Defender
        elif self._attacker_has_ai:
            if self._defender_has_ai:
                return None
            else:
                return Player.Attacker
        return Player.Defender

    def move_candidates(self) -> Iterable[CoordPair]:
        """Generate valid move candidates for the next player."""
        move = CoordPair()
        for (src,_) in self.player_units(self.next_player):
            move.src = src
            for dst in src.iter_adjacent():
                move.dst = dst
                if self.is_valid_move(move) or self.is_valid_to_attack(move) or self.is_valid_to_repair(move):
                    yield move.clone()
            move.dst = src
            yield move.clone()

    def get_moves_for_player(self, current_player:Player) -> Iterable[CoordPair]:
        """Generate valid move candidates for the given player."""
        move = CoordPair()
        for (src,_) in self.player_units(current_player):
            move.src = src
            for dst in src.iter_adjacent():
                move.dst = dst
                if self.is_valid_move(move) or self.is_valid_to_attack(move) or self.is_valid_to_repair(move):
                    yield move.clone()
            move.dst = src
            yield move.clone()

    def random_move(self) -> Tuple[int, CoordPair | None, float]:
        """Returns a random move."""
        move_candidates = list(self.move_candidates())
        random.shuffle(move_candidates)
        if len(move_candidates) > 0:
            return (0, move_candidates[0], 1)
        else:
            return (0, None, 0)

    def suggest_move(self, fileName) -> CoordPair | None:
        """Suggest the next move using minimax alpha beta. TODO: REPLACE RANDOM_MOVE WITH PROPER GAME LOGIC!!!"""
        outputFile = open(fileName, "a")
        start_time = datetime.now()
        (score, move) = self.minimax(self, self.options.max_depth, True, self.next_player, MIN_HEURISTIC_SCORE, MAX_HEURISTIC_SCORE)
        elapsed_seconds = (datetime.now() - start_time).total_seconds()
        if elapsed_seconds > self.options.max_time:
            outputFile.write("The computer took " + str(elapsed_seconds) + " to search, which exceeds the set time limit " + str(self.options.max_time) + ".\n")
            outputFile.close()
            return None
        outputFile.write("Time for this action: " + str(elapsed_seconds) + "\n")
        self.stats.total_seconds += elapsed_seconds
        print(f"Heuristic score: {score}")
        outputFile.write("Heuristic Score: " + str(score) + "\n")
        print(f"Evals per depth: ",end='')
        for k in sorted(self.stats.evaluations_per_depth.keys()):
            print(f"{k}:{self.stats.evaluations_per_depth[k]} ",end='')
        print()
        total_evals = sum(self.stats.evaluations_per_depth.values())
        if self.stats.total_seconds > 0:
            print(f"Eval perf.: {total_evals/self.stats.total_seconds/1000:0.1f}k/s")
        print(f"Elapsed time: {elapsed_seconds:0.1f}s")
        outputFile.write(self.get_cumulative_evals()[1] + "\n")
        outputFile.write(self.get_cumulative_evals_by_depth() + "\n")
        outputFile.write(self.get_cumulative_perc_evals() + "\n")
        outputFile.write(self.get_avg_branching_factor() + "\n")
        outputFile.close()
        return move

    def post_move_to_broker(self, move: CoordPair):
        """Send a move to the game broker."""
        if self.options.broker is None:
            return
        data = {
            "from": {"row": move.src.row, "col": move.src.col},
            "to": {"row": move.dst.row, "col": move.dst.col},
            "turn": self.turns_played
        }
        try:
            r = requests.post(self.options.broker, json=data)
            if r.status_code == 200 and r.json()['success'] and r.json()['data'] == data:
                # print(f"Sent move to broker: {move}")
                pass
            else:
                print(f"Broker error: status code: {r.status_code}, response: {r.json()}")
        except Exception as error:
            print(f"Broker error: {error}")

    def get_move_from_broker(self) -> CoordPair | None:
        """Get a move from the game broker."""
        if self.options.broker is None:
            return None
        headers = {'Accept': 'application/json'}
        try:
            r = requests.get(self.options.broker, headers=headers)
            if r.status_code == 200 and r.json()['success']:
                data = r.json()['data']
                if data is not None:
                    if data['turn'] == self.turns_played+1:
                        move = CoordPair(
                            Coord(data['from']['row'],data['from']['col']),
                            Coord(data['to']['row'],data['to']['col'])
                        )
                        print(f"Got move from broker: {move}")
                        return move
                    else:
                        # print("Got broker data for wrong turn.")
                        # print(f"Wanted {self.turns_played+1}, got {data['turn']}")
                        pass
                else:
                    # print("Got no data from broker")
                    pass
            else:
                print(f"Broker error: status code: {r.status_code}, response: {r.json()}")
        except Exception as error:
            print(f"Broker error: {error}")
        return None
    
    # Check if a unit can attack another unit
    def is_valid_to_attack(self, coords: CoordPair) -> bool:
        src = coords.src
        dst = coords.dst
        src_unit = self.get(src)
        dst_unit = self.get(dst)        
        
        if self.get(src) and self.get(dst) and self.is_adjacent(src, dst) and src_unit.player == self.next_player and src_unit.player != dst_unit.player:
            return True
        
        return False
    
    # Check if a unit can repair another unit
    def is_valid_to_repair(self, coords : CoordPair) -> bool:
        src = coords.src
        dst = coords.dst
        src_unit = self.get(src)
        dst_unit = self.get(dst)
        
        if self.get(src) and self.get(dst) and self.is_adjacent(src, dst) and src_unit.player == self.next_player and src_unit.player == dst_unit.player and src_unit.repair_amount(dst_unit) != 0 and dst_unit.health < 9:
            return True
        
        return False
            
    # Check if a unit can self-destruct
    def is_valid_to_self_destruct(self, coords: CoordPair) -> bool:
        src_unit = self.get(coords.src)

        if src_unit and src_unit.player == self.next_player:
            return coords.src == coords.dst
        
        return False
        
    # Attack action
    def attack(self, coords: CoordPair) -> None:
        src_unit = self.get(coords.src)
        dst_unit = self.get(coords.dst)
        
        attack_amount_src_to_dst = src_unit.damage_amount(dst_unit)
        attack_amount_dst_to_src = dst_unit.damage_amount(src_unit)
    
        self.mod_health(coords.src, - (attack_amount_dst_to_src))
        self.mod_health(coords.dst, - (attack_amount_src_to_dst))
        
   # Repair action 
    def repair(self, coords : CoordPair) -> None:
        src_unit = self.get(coords.src)
        dst_unit = self.get(coords.dst)

        repair_amount = src_unit.repair_amount(dst_unit)
        self.mod_health(coords.dst, repair_amount)
    
    # Self-destruct action
    def self_destruct(self, coords: CoordPair) -> None:
        itself = coords.src
        
        # self-destruct the unit
        self.mod_health(itself, -(self.get(itself).health))
        
        # damage surrounding units
        for coord in itself.iter_range(1):
            self.mod_health(coord, -2)
        
    # Check if a unit is adjacent to another unit
    def is_adjacent(self, src : Coord, dst: Coord) -> bool:
        if src.row == dst.row and abs(src.col - dst.col) == 1:
            return True
        if src.col == dst.col and abs(src.row - dst.row) == 1:
            return True
        return False
    
    # Create the output file name
    def create_file_name(self, b: str, t: str, m: str) -> str:
        fileName = "gameTrace" + "-" + b + "-" + t + "-" + m + ".txt"
        return fileName
    
    # Heuristic e0
    def heuristic_e0(self, board: Game, maximizing_player) -> int:
        virus_p1, tech_p1, firewall_p1, program_p1, ai_p1 = 0, 0, 0, 0, 0
        virus_p2, tech_p2, firewall_p2, program_p2, ai_p2 = 0, 0, 0, 0, 0
        
        for coord, unit in board.player_units(maximizing_player):
            if unit.type == UnitType.Virus:
                virus_p1 += 1
            elif unit.type == UnitType.Tech:
                tech_p1 += 1
            elif unit.type == UnitType.Firewall:
                firewall_p1 += 1
            elif unit.type == UnitType.Program:
                program_p1 += 1
            elif unit.type == UnitType.AI:
                ai_p1 += 1

        p1_score = (3 * (virus_p1 + tech_p1 + firewall_p1 + program_p1)) + (9999 * ai_p1)
        
        # Counting the number of different type of units of the opposite player
        for coord, unit in board.player_units(Player.Attacker if maximizing_player == Player.Defender else Player.Defender):
            if unit.type == UnitType.Virus:
                virus_p2 += 1
            elif unit.type == UnitType.Tech:
                tech_p2 += 1
            elif unit.type == UnitType.Firewall:
                firewall_p2 += 1
            elif unit.type == UnitType.Program:
                program_p2 += 1
            elif unit.type == UnitType.AI:
                ai_p2 += 1
                 
        p2_score = (3 * (virus_p2 + tech_p2 + firewall_p2 + program_p2)) + (9999 * ai_p2)

        return p1_score - p2_score
    
    # Heuristic e1 - Total number of unit and AI Safety
    # This heuristic considers the number of units left and evaluates the safety of the unit AI. A player with more units left and an AI unit with fewer threats against it is preferable.
    def heuristic_e1(self, board: Game, maximizing_player) -> int:
        p1_ai, p2_ai = 0, 0
        p1_score, p2_score = 0, 0
        p1_number_of_unit, p2_number_of_unit = 0, 0

        for coord, unit in board.player_units(maximizing_player):
            p1_number_of_unit += 1
            if unit.type == UnitType.AI:
                p1_ai += 1
                if (board.is_engaged_in_combat(coord)):
                    p1_score -= 100

        p1_score += (p1_number_of_unit + 9999 * p1_ai)
        
        for coord, unit in board.player_units(Player.Attacker if maximizing_player == Player.Defender else Player.Defender):
            p2_number_of_unit += 1
            if unit.type == UnitType.AI:
                p2_ai += 1
                if (board.is_engaged_in_combat(coord)):
                    p2_score -= 100
                 
        p2_score += (p2_number_of_unit + 9999 * p2_ai)

        return p1_score - p2_score
    
     # Heuristic e2 - Unit Mobilitiy
     # This heuristic priortizes certains units pieces such as Virus and Tech because they have more mobility, having these pieces with high mobility is an advantage.
    def heuristic_e2(self, board: Game, maximizing_player) -> int:
        opponent = Player.Attacker if maximizing_player == Player.Defender else Player.Defender
        ai_p1, ai_p2, virus_p1, virus_p2, tech_p1, tech_p2 = 0, 0, 0, 0, 0, 0
        p1_score, p2_score = 0, 0

        for coord, unit in board.player_units(maximizing_player):
            if unit.type == UnitType.AI:
                ai_p1 += 1
            if unit.type == UnitType.Virus:
                virus_p1 += 1
            if unit.type == UnitType.Tech:
                tech_p1 += 1

        p1_score += 9999 * ai_p1 + 1000 * virus_p1 + 1000 * tech_p1
        
        for coord, unit in board.player_units(opponent):
            if unit.type == UnitType.AI:
                ai_p2 += 1
            if unit.type == UnitType.Virus:
                virus_p2 += 1
            if unit.type == UnitType.Tech:
                tech_p2 += 1
                 
        p2_score += 9999 * ai_p2 + 1000 * virus_p2 + 1000 * tech_p2

        number_of_legal_moves_for_maximizing_player = len(list(board.get_moves_for_player(maximizing_player)))
        number_of_legal_moves_for_opponent_player = len(list(board.get_moves_for_player(opponent)))
        
        return (p1_score - p2_score) + (number_of_legal_moves_for_maximizing_player - number_of_legal_moves_for_opponent_player)
    
    
    # Minimax Algorithm
    def minimax(self, game : Game, depth, is_maximizing_player, maximizing_player, alpha, beta) -> Tuple[int, CoordPair | None, int]:
        global nb_of_leaf_nodes
        if depth == 0 or game.has_winner():
            nb_of_leaf_nodes += 1
            if self.options.heuristic == "e1":
                return (self.heuristic_e1(game, maximizing_player), None)
            elif self.options.heuristic == "e2":
                return (self.heuristic_e2(game, maximizing_player), None)
            else:
                return (self.heuristic_e0(game, maximizing_player), None)
            
        moves = list(game.move_candidates())
        
        if is_maximizing_player:
            max_eval = MIN_HEURISTIC_SCORE
            best_move = None
            for move in moves:
                map[depth] = map.get(depth, 0) + 1
                temp_game = game.clone()
                (success, result) = temp_game.perform_move(move)
                if success:
                    temp_game.next_turn()
                    current_eval = self.minimax(temp_game, depth-1, False, maximizing_player, alpha, beta)[0]

                    if current_eval > max_eval:
                        max_eval = current_eval
                        best_move = move
                    
                    if game.options.alpha_beta:
                        alpha = max(alpha, current_eval)
                        if beta <= alpha:
                            break

            return (max_eval, best_move)
        else:
            min_eval = MAX_HEURISTIC_SCORE
            best_move = None
            for move in moves:
                map[depth] = map.get(depth, 0) + 1
                temp_game = game.clone()
                (success, result) = temp_game.perform_move(move)
                if success:
                    temp_game.next_turn()
                    current_eval = self.minimax(temp_game, depth-1, True, maximizing_player, alpha, beta)[0]
                    
                    if current_eval < min_eval:
                        min_eval = current_eval
                        best_move = move
                    
                    if game.options.alpha_beta:
                        beta = min(beta, current_eval)
                        if beta <= alpha:
                            break

            return (min_eval, best_move)
    
    def get_cumulative_evals(self) -> Tuple[int, str]:
        count = 0
        sorted_map = self.sort_map()
        for value in sorted_map.values():
            count += value
        return (count, "Cumulative evals: " + str(count))
    
    def get_cumulative_evals_by_depth(self) -> str:
        res = ""
        sorted_map = self.sort_map()
        last_key = list(sorted_map)[-1]
        for key, value in sorted_map.items():
            if last_key == key: 
                res += str(key) + "=" + str(value)
            else:
                res += str(key) + "=" + str(value) + " "
        return "Cumulative evals by depth: " + res
    
    def get_cumulative_perc_evals(self) -> str:
        res = ""
        total = self.get_cumulative_evals()[0]
        sorted_map = self.sort_map()
        last_key = list(sorted_map)[-1]
        for key, value in sorted_map.items():
            if last_key == key:
                res += str(key) + "=" + str(round(float((value / total) * 100), 1)) + "%"
            else:
                res += str(key) + "=" + str(round(float((value / total) * 100), 1)) + "% "
        return "Cumulative '%' evals by depth: " + res
    
    
    def get_avg_branching_factor(self) -> str:
        nb_of_non_root_nodes = self.get_cumulative_evals()[0] - 1
        nb_of_non_leaf_nodes = self.get_cumulative_evals()[0] - nb_of_leaf_nodes
        avg_branching_factor = round(float(nb_of_non_root_nodes / nb_of_non_leaf_nodes), 2)
        return "Average branching factor: " + str(avg_branching_factor)
    
    def sort_map(self) -> dict:
        limit = self.options.max_depth + 1
        sorted_map = {key: map[limit - key] for key in range(1, limit)}
        return sorted_map

##############################################################################################################

def main():
    try:
        # parse command line arguments
        parser = argparse.ArgumentParser(
            prog='ai_wargame',
            formatter_class=argparse.ArgumentDefaultsHelpFormatter)
        parser.add_argument('max_depth', type=int, help='maximum search depth')
        parser.add_argument('max_time', type=float, help='maximum search time')
        parser.add_argument('max_turns', type=int, help='maximum number of turns')
        parser.add_argument('alpha_beta', type=str.lower, help='whether alpha-beta is on or off')
        parser.add_argument('game_type', type=str, default="manual", help='game type: auto|attacker|defender|manual')
        parser.add_argument('--heuristic', type=str, default="e0", help='heuristic: e0|e1|e1')
        parser.add_argument('--broker', type=str, help='play via a game broker')
        args = parser.parse_args()

        # parse the game type
        if args.game_type == "attacker":
            game_type = GameType.AttackerVsComp
        elif args.game_type == "defender":
            game_type = GameType.CompVsDefender
        elif args.game_type == "manual":
            game_type = GameType.AttackerVsDefender
        else:
            game_type = GameType.CompVsComp
        
        # set up game options
        options = Options(game_type=game_type)

        # override class defaults via command line options
        if args.max_depth is not None:
            options.max_depth = args.max_depth
        if args.max_time is not None:
            options.max_time = args.max_time
        if args.broker is not None:
            options.broker = args.broker
        if args.max_turns is not None:
            options.max_turns = args.max_turns
        if args.alpha_beta is not None:
            options.alpha_beta = True if args.alpha_beta == "true" else False
        if args.heuristic is not None:
            options.heuristic = args.heuristic

    except SystemExit:
        print("Please input the valid game parameters in the correct format.")
        exit(1)
    
    try:
        # create a new game
        game = Game(options=options)
        fileName = game.create_file_name(str(options.alpha_beta), str(options.max_time), str(options.max_turns))
        outputFile = open(fileName, "x")
        outputFile.write("===== The Game Parameters =====\n")
        outputFile.write("The value of the timeout in seconds: " + str(options.max_time) + "\n")
        outputFile.write("The max number of turns: " + str(options.max_turns) + "\n")
        outputFile.write("Play mode: " + options.game_type.name + "\n")
        if options.game_type != GameType.AttackerVsDefender:
            outputFile.write("Alpha-beta: " + str(options.alpha_beta) + "\n")
            outputFile.write("Heuristic: " + str(options.heuristic) + "\n\n")
        outputFile.write("======================\n")
        outputFile.write("   The game starts!\n")
        outputFile.write("======================\n")
        outputFile.write(game.to_string())
        outputFile.write("\n")
        
        # the main game loop
        while True:
            if outputFile.closed:
                outputFile = open(fileName, "a")
            print()
            print(game)
            winner = game.has_winner()
            if winner is not None:
                print(f"{winner.name} wins!")
                outputFile.write(f"{winner.name} wins in " + str(game.turns_played) + " turns!")
                break
            if game.options.game_type == GameType.AttackerVsDefender:
                outputFile.write(game.next_player.name + game.human_turn() + "\n\n")
            elif game.options.game_type == GameType.AttackerVsComp and game.next_player == Player.Attacker:
                outputFile.write(game.next_player.name + game.human_turn() + "\n\n")
            elif game.options.game_type == GameType.CompVsDefender and game.next_player == Player.Defender:
                outputFile.write(game.next_player.name + game.human_turn() + "\n\n")
            else:
                player = game.next_player
                outputFile.close()
                move = game.computer_turn(fileName)
                if move is not None:
                    game.post_move_to_broker(move)
                else:
                    if outputFile.closed:
                        outputFile = open(fileName, "a")
                    print("Computer exceed the time limit to return its moves.")
                    outputFile.write("Computer exceed the time limit to return its moves." + "\n")
                    if game.next_player == Player.Attacker:
                        outputFile.write("Defender won!")
                        print("Defender won!")
                    else:
                        outputFile.write("Attacker won!")
                        print("Attacker won!")
                    outputFile.close()
                    exit(1)
            if outputFile.closed:
                outputFile = open(fileName, "a")
            outputFile.write(game.to_string())
            outputFile.write("\n")
            print("=============================================")
        outputFile.close()
    except FileExistsError:
        print("The outpufile already exists. The existing file will be deleted. Please try running the game again!")
        os.remove(fileName)
        exit(1)
##############################################################################################################

if __name__ == '__main__':
    main()
