"""Игра "Танчики" в стиле Денди на Pygame.

Файл автономный, запускается напрямую:
    python "start V.0.700.40.py"

Управление:
    Стрелки — движение
    SPACE — огонь
    Enter — подтвердить на экранах меню
    Esc — выход
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Iterable, List, Optional, Tuple

import pygame

# ==== Общие настройки ====
FPS = 60
TILE_SIZE = 24
GRID_SIZE = 26  # поле 26x26, как в оригинальной игре
PLAY_AREA_WIDTH = GRID_SIZE * TILE_SIZE
PLAY_AREA_HEIGHT = GRID_SIZE * TILE_SIZE
PANEL_WIDTH = 200
SCREEN_WIDTH = PLAY_AREA_WIDTH + PANEL_WIDTH
SCREEN_HEIGHT = PLAY_AREA_HEIGHT

PLAYER_LIVES = 3
PLAYER_SPEED = 96.0
PLAYER_FIRE_DELAY = 0.35
PLAYER_BULLET_SPEED = 360.0

ENEMY_BASE_COUNT = 16
ENEMY_PER_STAGE = 4
MAX_TOTAL_ENEMIES = 40
MAX_ACTIVE_ENEMIES = 4
ENEMY_FIRE_DELAY = (1.1, 2.2)
ENEMY_DIRECTION_DELAY = (1.4, 3.0)

# ==== Цвета ====
BG_COLOR = (18, 20, 26)
PANEL_BG = (26, 28, 36)
PANEL_ACCENT = (96, 160, 240)
PANEL_TEXT = (220, 220, 220)
PLAYER_COLOR = (224, 224, 64)
PLAYER_SHADOW = (140, 140, 40)
BULLET_COLOR = (255, 184, 64)
ENEMY_COLORS = {
    "basic": (206, 74, 74),
    "fast": (212, 160, 70),
    "heavy": (128, 192, 200),
}

# ==== Карта уровня (26x26) ====
LEVEL_LAYOUT = """
..........................
....##..............##....
....##....WWWW....##......
..####....WWWW....####....
..#..#............#..#....
..#..#...FFFF...##..#.....
......S..FFFF..S..........
..####............####....
..####..######..####......
......#..W..W..#..........
..S...#..W..W..#...S......
..S...#..W..W..#...S......
......#........#..........
..####....SS....####......
..####............####....
......##.FFFF.##..........
..S.....FFFF.....S........
..S....######....S........
......##....##............
..####..............####..
..####..######..####......
..........................
.........######...........
.........#....#...........
.........#....#...........
...........BB.............
"""


class Direction(Enum):
    UP = (0, -1)
    RIGHT = (1, 0)
    DOWN = (0, 1)
    LEFT = (-1, 0)

    @property
    def vector(self) -> pygame.Vector2:
        return pygame.Vector2(self.value)


class TileType(Enum):
    BRICK = "brick"
    STEEL = "steel"
    WATER = "water"
    FOREST = "forest"
    ICE = "ice"
    BASE = "base"
    BASE_RUIN = "base_ruin"


@dataclass(frozen=True)
class TileDefinition:
    tile_type: TileType
    color: Tuple[int, int, int]
    passable: bool
    bullet_block: bool
    destructible: bool
    overlay: bool = False


TILE_DEFINITIONS: Dict[TileType, TileDefinition] = {
    TileType.BRICK: TileDefinition(TileType.BRICK, (198, 92, 42), False, True, True),
    TileType.STEEL: TileDefinition(TileType.STEEL, (150, 150, 160), False, True, False),
    TileType.WATER: TileDefinition(TileType.WATER, (54, 120, 206), False, True, False),
    TileType.FOREST: TileDefinition(TileType.FOREST, (54, 140, 66), True, False, False, True),
    TileType.ICE: TileDefinition(TileType.ICE, (180, 200, 220), True, False, False),
    TileType.BASE: TileDefinition(TileType.BASE, (210, 200, 120), False, True, False),
    TileType.BASE_RUIN: TileDefinition(TileType.BASE_RUIN, (110, 60, 60), False, True, False),
}

CHAR_TO_TILE: Dict[str, Optional[TileType]] = {
    "#": TileType.BRICK,
    "S": TileType.STEEL,
    "W": TileType.WATER,
    "F": TileType.FOREST,
    "I": TileType.ICE,
    "B": TileType.BASE,
    ".": None,
}


@dataclass
class Tile:
    grid_x: int
    grid_y: int
    definition: TileDefinition
    rect: pygame.Rect

    def set_definition(self, definition: TileDefinition) -> None:
        self.definition = definition


def parse_level_layout(raw: str) -> List[str]:
    rows = [row.rstrip() for row in raw.strip().splitlines()]
    width = max(len(row) for row in rows)
    return [row.ljust(width, ".") for row in rows]


class Level:
    def __init__(self, layout: List[str]):
        self.layout = layout
        self.width = len(layout[0])
        self.height = len(layout)
        if self.width != GRID_SIZE or self.height != GRID_SIZE:
            raise ValueError("Макет уровня должен быть 26x26 для корректной работы")
        self.pixel_width = self.width * TILE_SIZE
        self.pixel_height = self.height * TILE_SIZE
        self.tiles: Dict[Tuple[int, int], Tile] = {}
        self.base_tiles: List[Tile] = []
        self.overlay_tiles: List[Tile] = []
        self.base_alive = True
        self._build_tiles()

    def _build_tiles(self) -> None:
        for y, row in enumerate(self.layout):
            for x, ch in enumerate(row):
                tile_type = CHAR_TO_TILE.get(ch)
                if tile_type is None:
                    continue
                definition = TILE_DEFINITIONS[tile_type]
                rect = pygame.Rect(x * TILE_SIZE, y * TILE_SIZE, TILE_SIZE, TILE_SIZE)
                tile = Tile(x, y, definition, rect)
                self.tiles[(x, y)] = tile
                if tile.definition.overlay:
                    self.overlay_tiles.append(tile)
                if tile_type == TileType.BASE:
                    self.base_tiles.append(tile)

    def iter_tiles(self, rect: pygame.Rect) -> Iterable[Tile]:
        left = max(rect.left // TILE_SIZE, 0)
        right = min((rect.right - 1) // TILE_SIZE, self.width - 1)
        top = max(rect.top // TILE_SIZE, 0)
        bottom = min((rect.bottom - 1) // TILE_SIZE, self.height - 1)
        for gy in range(top, bottom + 1):
            for gx in range(left, right + 1):
                tile = self.tiles.get((gx, gy))
                if tile is not None:
                    yield tile

    def is_rect_blocked(self, rect: pygame.Rect) -> bool:
        if rect.left < 0 or rect.top < 0:
            return True
        if rect.right > self.pixel_width or rect.bottom > self.pixel_height:
            return True
        for tile in self.iter_tiles(rect):
            if not tile.definition.passable:
                return True
        return False

    def handle_bullet_collision(self, rect: pygame.Rect) -> Optional[str]:
        for tile in list(self.iter_tiles(rect)):
            definition = tile.definition
            if tile.definition.tile_type == TileType.FOREST:
                continue
            if tile.definition.tile_type == TileType.ICE:
                continue
            if not definition.bullet_block:
                continue
            if definition.tile_type == TileType.BASE:
                if self.base_alive:
                    self.base_alive = False
                    for base_tile in self.base_tiles:
                        base_tile.set_definition(TILE_DEFINITIONS[TileType.BASE_RUIN])
                    return "base"
            if definition.destructible:
                self.tiles.pop((tile.grid_x, tile.grid_y), None)
                if tile in self.overlay_tiles:
                    self.overlay_tiles.remove(tile)
                return "brick"
            return "block"
        return None

    def draw(self, surface: pygame.Surface) -> None:
        for tile in self.tiles.values():
            if tile.definition.overlay:
                continue
            pygame.draw.rect(surface, tile.definition.color, tile.rect)
            if tile.definition.tile_type == TileType.BASE_RUIN:
                pygame.draw.line(surface, (40, 20, 20), tile.rect.topleft, tile.rect.bottomright, 3)
                pygame.draw.line(surface, (40, 20, 20), tile.rect.topright, tile.rect.bottomleft, 3)
            if tile.definition.tile_type == TileType.WATER:
                inner = tile.rect.inflate(-6, -6)
                pygame.draw.rect(surface, (84, 160, 240), inner, border_radius=4)
            if tile.definition.tile_type == TileType.STEEL:
                inner = tile.rect.inflate(-6, -6)
                pygame.draw.rect(surface, (210, 210, 220), inner, 2)

    def draw_overlay(self, surface: pygame.Surface) -> None:
        for tile in self.overlay_tiles:
            pygame.draw.rect(surface, tile.definition.color, tile.rect)


class Bullet:
    SIZE = 6

    def __init__(self, position: pygame.Vector2, direction: Direction, speed: float, owner: "Tank", friendly: bool):
        self.position = pygame.Vector2(position)
        self.direction = direction
        self.speed = speed
        self.owner = owner
        self.friendly = friendly
        self.rect = pygame.Rect(0, 0, self.SIZE, self.SIZE)
        self.rect.center = (round(self.position.x), round(self.position.y))

    def update(self, dt: float) -> None:
        self.position += self.direction.vector * self.speed * dt
        self.rect.center = (round(self.position.x), round(self.position.y))

    def draw(self, surface: pygame.Surface) -> None:
        pygame.draw.rect(surface, BULLET_COLOR, self.rect)


class Tank:
    def __init__(
        self,
        x: float,
        y: float,
        color: Tuple[int, int, int],
        speed: float,
        fire_delay: float,
        bullet_speed: float,
        friendly: bool,
    ):
        self.pos = pygame.Vector2(x, y)
        self.rect = pygame.Rect(int(x), int(y), TILE_SIZE, TILE_SIZE)
        self.color = color
        self.speed = speed
        self.fire_delay = fire_delay
        self.bullet_speed = bullet_speed
        self.friendly = friendly
        self.direction = Direction.UP
        self.cooldown_timer = 0.0
        self.invulnerable_timer = 0.0
        self.max_bullets = 1
        self.active_bullets = 0
        self.health = 1

    def update_timers(self, dt: float) -> None:
        if self.cooldown_timer > 0:
            self.cooldown_timer = max(0.0, self.cooldown_timer - dt)
        if self.invulnerable_timer > 0:
            self.invulnerable_timer = max(0.0, self.invulnerable_timer - dt)

    def _try_axis_move(self, dx: float, dy: float, level: Level, others: Iterable["Tank"]) -> bool:
        moved = False
        if dx != 0:
            new_pos_x = self.pos.x + dx
            test_rect = pygame.Rect(int(round(new_pos_x)), int(round(self.pos.y)), self.rect.width, self.rect.height)
            if not level.is_rect_blocked(test_rect) and not self._collides_with_others(test_rect, others):
                self.pos.x = new_pos_x
                moved = True
        if dy != 0:
            new_pos_y = self.pos.y + dy
            test_rect = pygame.Rect(int(round(self.pos.x)), int(round(new_pos_y)), self.rect.width, self.rect.height)
            if not level.is_rect_blocked(test_rect) and not self._collides_with_others(test_rect, others):
                self.pos.y = new_pos_y
                moved = True
        self.rect.topleft = (int(round(self.pos.x)), int(round(self.pos.y)))
        return moved

    @staticmethod
    def _collides_with_others(rect: pygame.Rect, others: Iterable["Tank"]) -> bool:
        for other in others:
            if getattr(other, "active", True) and rect.colliderect(other.rect):
                return True
        return False

    def move(self, direction: Direction, dt: float, level: Level, others: Iterable["Tank"]) -> bool:
        self.direction = direction
        vec = direction.vector * self.speed * dt
        return self._try_axis_move(vec.x, vec.y, level, others)

    def can_fire(self) -> bool:
        return self.cooldown_timer <= 0 and self.active_bullets < self.max_bullets

    def fire(self) -> Optional[Bullet]:
        if not self.can_fire():
            return None
        muzzle = pygame.Vector2(self.rect.center)
        muzzle += self.direction.vector * (self.rect.width / 2 + Bullet.SIZE / 2)
        bullet = Bullet(muzzle, self.direction, self.bullet_speed, self, self.friendly)
        self.cooldown_timer = self.fire_delay
        self.active_bullets += 1
        return bullet

    def on_bullet_destroyed(self) -> None:
        if self.active_bullets > 0:
            self.active_bullets -= 1

    def take_damage(self, amount: int = 1) -> bool:
        self.health -= amount
        return self.health <= 0

    def draw(self, surface: pygame.Surface) -> None:
        base_color = self.color
        if self.invulnerable_timer > 0 and int(self.invulnerable_timer * 5) % 2 == 0:
            base_color = (240, 240, 240)
        pygame.draw.rect(surface, base_color, self.rect)
        inner = self.rect.inflate(-6, -6)
        pygame.draw.rect(surface, (0, 0, 0), inner, 2)
        barrel_start = pygame.Vector2(self.rect.center)
        barrel_end = barrel_start + self.direction.vector * (self.rect.width // 2)
        pygame.draw.line(surface, (0, 0, 0), barrel_start, barrel_end, 4)


class PlayerTank(Tank):
    def __init__(self, x: float, y: float):
        super().__init__(x, y, PLAYER_COLOR, PLAYER_SPEED, PLAYER_FIRE_DELAY, PLAYER_BULLET_SPEED, True)
        self.spawn_point = pygame.Vector2(x, y)
        self.lives = PLAYER_LIVES
        self.active = True
        self.dead = False
        self.respawn_delay = 1.6
        self.respawn_timer = 0.0

    def reset_position(self, x: float, y: float) -> None:
        self.spawn_point.update(x, y)
        self.pos.update(x, y)
        self.rect.topleft = (int(x), int(y))
        self.direction = Direction.UP
        self.cooldown_timer = 0.0
        self.invulnerable_timer = 2.0
        self.active_bullets = 0
        self.active = True
        self.dead = False
        self.respawn_timer = 0.0

    def start_respawn(self) -> None:
        self.dead = True
        self.active = False
        self.respawn_timer = self.respawn_delay
        self.invulnerable_timer = 0.0

    def update_respawn(self, dt: float, level: Level, enemies: Iterable[Tank]) -> None:
        if not self.dead:
            return
        self.respawn_timer = max(0.0, self.respawn_timer - dt)
        if self.respawn_timer > 0:
            return
        spawn_rect = pygame.Rect(int(self.spawn_point.x), int(self.spawn_point.y), self.rect.width, self.rect.height)
        if level.is_rect_blocked(spawn_rect):
            self.respawn_timer = 0.25
            return
        for enemy in enemies:
            if spawn_rect.colliderect(enemy.rect):
                self.respawn_timer = 0.25
                return
        self.pos.update(self.spawn_point)
        self.rect.topleft = (int(self.spawn_point.x), int(self.spawn_point.y))
        self.direction = Direction.UP
        self.dead = False
        self.active = True
        self.invulnerable_timer = 2.5
        self.cooldown_timer = 0.0
        self.active_bullets = 0

    def draw(self, surface: pygame.Surface) -> None:
        if not self.active:
            return
        shadow_rect = self.rect.copy()
        shadow_rect.topleft = (shadow_rect.left + 2, shadow_rect.top + 2)
        pygame.draw.rect(surface, PLAYER_SHADOW, shadow_rect)
        super().draw(surface)


class EnemyTank(Tank):
    SCORE_VALUES = {
        "basic": 100,
        "fast": 150,
        "heavy": 300,
    }

    def __init__(self, x: float, y: float, variant: str = "basic"):
        speed = 84.0
        fire_delay = 0.55
        bullet_speed = 280.0
        if variant == "fast":
            speed = 112.0
            fire_delay = 0.42
            bullet_speed = 320.0
        elif variant == "heavy":
            speed = 72.0
            fire_delay = 0.65
            bullet_speed = 300.0
        super().__init__(x, y, ENEMY_COLORS[variant], speed, fire_delay, bullet_speed, False)
        self.variant = variant
        self.health = 2 if variant == "heavy" else 1
        self.change_dir_timer = random.uniform(*ENEMY_DIRECTION_DELAY)
        self.fire_timer = random.uniform(*ENEMY_FIRE_DELAY)
        self.score_value = self.SCORE_VALUES[variant]
        self.invulnerable_timer = 1.0

    def update_ai(self, dt: float, level: Level, player: PlayerTank, enemies: Iterable["EnemyTank"]) -> Optional[Bullet]:
        self.update_timers(dt)
        self.change_dir_timer -= dt
        moved = False
        if self.change_dir_timer <= 0:
            self.direction = random.choice(list(Direction))
            self.change_dir_timer = random.uniform(*ENEMY_DIRECTION_DELAY)
        target_list = [enemy for enemy in enemies if enemy is not self]
        if player.active:
            target_list.append(player)
        moved = self.move(self.direction, dt, level, target_list)
        if not moved:
            self.direction = random.choice(list(Direction))
            self.change_dir_timer = random.uniform(0.4, 1.0)
        self.fire_timer -= dt
        should_fire = False
        if self.fire_timer <= 0:
            self.fire_timer = random.uniform(*ENEMY_FIRE_DELAY)
            should_fire = True
        if should_fire:
            bullet = self.fire()
            if bullet is not None:
                return bullet
        return None


class Game:
    def __init__(self) -> None:
        pygame.init()
        pygame.font.init()
        pygame.display.set_caption("Танчики — Денди ремейк")
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        self.clock = pygame.time.Clock()
        self.font_small = pygame.font.SysFont("Consolas", 18)
        self.font_medium = pygame.font.SysFont("Consolas", 24)
        self.font_large = pygame.font.SysFont("Consolas", 48)
        self.running = True
        self.state = "menu"
        self.stage = 1
        self.score = 0
        self.level = Level(parse_level_layout(LEVEL_LAYOUT))
        self.player = PlayerTank(TILE_SIZE * 12, TILE_SIZE * 23)
        self.player.active = False
        self.enemies: List[EnemyTank] = []
        self.bullets: List[Bullet] = []
        self.remaining_enemies = 0
        self.enemy_spawn_timer = 0.0
        self.game_over_reason: Optional[str] = None

    def start_new_game(self) -> None:
        self.stage = 1
        self.score = 0
        self.player = PlayerTank(TILE_SIZE * 12, TILE_SIZE * 23)
        self.prepare_stage(reset_lives=True)

    def prepare_stage(self, reset_lives: bool = False) -> None:
        self.level = Level(parse_level_layout(LEVEL_LAYOUT))
        self.enemies.clear()
        self.bullets.clear()
        base_count = ENEMY_BASE_COUNT + (self.stage - 1) * ENEMY_PER_STAGE
        self.remaining_enemies = min(base_count, MAX_TOTAL_ENEMIES)
        self.enemy_spawn_timer = 2.0
        if reset_lives:
            self.player.lives = PLAYER_LIVES
        self.player.reset_position(TILE_SIZE * 12, TILE_SIZE * 23)
        self.player.invulnerable_timer = 2.5
        self.state = "playing"
        self.game_over_reason = None

    def spawn_enemy(self) -> bool:
        if self.remaining_enemies <= 0:
            return False
        if len(self.enemies) >= MAX_ACTIVE_ENEMIES:
            return False
        spawn_points = [
            (TILE_SIZE, TILE_SIZE),
            (TILE_SIZE * 12, TILE_SIZE),
            (TILE_SIZE * 23, TILE_SIZE),
        ]
        random.shuffle(spawn_points)
        variants = ["basic", "fast", "heavy"]
        for spawn in spawn_points:
            rect = pygame.Rect(spawn[0], spawn[1], TILE_SIZE, TILE_SIZE)
            if self.level.is_rect_blocked(rect):
                continue
            blocked = False
            if self.player.active and rect.colliderect(self.player.rect):
                blocked = True
            if not blocked:
                for enemy in self.enemies:
                    if rect.colliderect(enemy.rect):
                        blocked = True
                        break
            if blocked:
                continue
            variant = random.choices(variants, weights=[0.6, 0.25, 0.15], k=1)[0]
            enemy = EnemyTank(spawn[0], spawn[1], variant)
            self.enemies.append(enemy)
            self.remaining_enemies -= 1
            return True
        return False

    def handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    if self.state == "menu":
                        self.start_new_game()
                    elif self.state == "game_over":
                        self.start_new_game()
                    elif self.state == "victory":
                        self.stage += 1
                        self.prepare_stage(reset_lives=False)

    def handle_player_input(self, dt: float) -> None:
        keys = pygame.key.get_pressed()
        direction: Optional[Direction] = None
        if keys[pygame.K_UP]:
            direction = Direction.UP
        elif keys[pygame.K_DOWN]:
            direction = Direction.DOWN
        elif keys[pygame.K_LEFT]:
            direction = Direction.LEFT
        elif keys[pygame.K_RIGHT]:
            direction = Direction.RIGHT
        if direction is not None:
            self.player.move(direction, dt, self.level, self.enemies)
        if keys[pygame.K_SPACE]:
            bullet = self.player.fire()
            if bullet is not None:
                self.bullets.append(bullet)

    def update_bullets(self, dt: float) -> None:
        play_rect = pygame.Rect(0, 0, PLAY_AREA_WIDTH, PLAY_AREA_HEIGHT)
        for bullet in list(self.bullets):
            bullet.update(dt)
            if not play_rect.contains(bullet.rect):
                self.remove_bullet(bullet)
                continue
            collision = self.level.handle_bullet_collision(bullet.rect)
            if collision is not None:
                self.remove_bullet(bullet)
                if collision == "base" and self.state == "playing":
                    self.state = "game_over"
                    self.game_over_reason = "base"
                continue
            if bullet.friendly:
                target_hit = None
                for enemy in self.enemies:
                    if enemy.invulnerable_timer > 0:
                        continue
                    if bullet.rect.colliderect(enemy.rect):
                        target_hit = enemy
                        break
                if target_hit is not None:
                    if target_hit.take_damage():
                        self.enemies.remove(target_hit)
                        self.score += target_hit.score_value
                    self.remove_bullet(bullet)
                    continue
            else:
                if self.player.active and self.player.invulnerable_timer <= 0 and bullet.rect.colliderect(self.player.rect):
                    self.remove_bullet(bullet)
                    self.on_player_hit()
                    continue
            # проверка столкновений пуль между собой
        to_remove: List[Bullet] = []
        for i, bullet_a in enumerate(self.bullets):
            for bullet_b in self.bullets[i + 1 :]:
                if bullet_a.friendly == bullet_b.friendly:
                    continue
                if bullet_a.rect.colliderect(bullet_b.rect):
                    if bullet_a not in to_remove:
                        to_remove.append(bullet_a)
                    if bullet_b not in to_remove:
                        to_remove.append(bullet_b)
        for bullet in to_remove:
            self.remove_bullet(bullet)

    def remove_bullet(self, bullet: Bullet) -> None:
        if bullet in self.bullets:
            self.bullets.remove(bullet)
            bullet.owner.on_bullet_destroyed()

    def on_player_hit(self) -> None:
        if self.player.invulnerable_timer > 0 or not self.player.active:
            return
        self.player.lives -= 1
        if self.player.lives <= 0:
            self.player.lives = 0
            self.state = "game_over"
            self.game_over_reason = "player"
        else:
            self.player.start_respawn()

    def update(self, dt: float) -> None:
        if self.state != "playing":
            return
        self.player.update_timers(dt)
        if self.player.dead:
            self.player.update_respawn(dt, self.level, self.enemies)
        else:
            self.handle_player_input(dt)
        for enemy in list(self.enemies):
            bullet = enemy.update_ai(dt, self.level, self.player, self.enemies)
            if bullet is not None:
                self.bullets.append(bullet)
        self.update_bullets(dt)
        if self.remaining_enemies > 0:
            self.enemy_spawn_timer -= dt
            if self.enemy_spawn_timer <= 0:
                spawned = self.spawn_enemy()
                self.enemy_spawn_timer = 1.5 if spawned else 0.5
        if self.level.base_alive is False and self.state == "playing":
            self.state = "game_over"
            self.game_over_reason = "base"
        if self.remaining_enemies == 0 and not self.enemies and self.state == "playing":
            self.state = "victory"

    def draw_panel(self) -> None:
        panel_rect = pygame.Rect(PLAY_AREA_WIDTH, 0, PANEL_WIDTH, SCREEN_HEIGHT)
        pygame.draw.rect(self.screen, PANEL_BG, panel_rect)
        pygame.draw.rect(self.screen, PANEL_ACCENT, panel_rect, 2)
        lines = [
            f"Этап: {self.stage}",
            f"Очки: {self.score}",
            f"Жизни: {self.player.lives}",
            f"Враги: {self.remaining_enemies + len(self.enemies)}",
        ]
        for i, line in enumerate(lines):
            text = self.font_medium.render(line, True, PANEL_TEXT)
            self.screen.blit(text, (PLAY_AREA_WIDTH + 16, 24 + i * 36))
        if self.state == "menu":
            hint_lines = [
                "Стрелки — движение",
                "Пробел — огонь",
                "Enter — начать",
            ]
            for i, line in enumerate(hint_lines):
                text = self.font_small.render(line, True, (180, 180, 200))
                self.screen.blit(text, (PLAY_AREA_WIDTH + 16, 200 + i * 26))
        else:
            text = self.font_small.render("ESC — выход", True, (160, 160, 180))
            self.screen.blit(text, (PLAY_AREA_WIDTH + 16, SCREEN_HEIGHT - 40))

    def draw_state_overlay(self) -> None:
        if self.state == "playing":
            return
        overlay = pygame.Surface((PLAY_AREA_WIDTH, PLAY_AREA_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0, 0))
        if self.state == "menu":
            title = self.font_large.render("Танчики", True, (255, 220, 120))
            subtitle = self.font_medium.render("Нажмите Enter для начала", True, (240, 240, 240))
            self.screen.blit(title, title.get_rect(center=(PLAY_AREA_WIDTH // 2, PLAY_AREA_HEIGHT // 2 - 40)))
            self.screen.blit(subtitle, subtitle.get_rect(center=(PLAY_AREA_WIDTH // 2, PLAY_AREA_HEIGHT // 2 + 20)))
        elif self.state == "game_over":
            title = self.font_large.render("Поражение", True, (255, 100, 100))
            reason = "База уничтожена" if self.game_over_reason == "base" else "Танк разбит"
            subtitle = self.font_medium.render(reason, True, (240, 240, 240))
            hint = self.font_small.render("Enter — сыграть ещё", True, (220, 220, 220))
            self.screen.blit(title, title.get_rect(center=(PLAY_AREA_WIDTH // 2, PLAY_AREA_HEIGHT // 2 - 40)))
            self.screen.blit(subtitle, subtitle.get_rect(center=(PLAY_AREA_WIDTH // 2, PLAY_AREA_HEIGHT // 2 + 10)))
            self.screen.blit(hint, hint.get_rect(center=(PLAY_AREA_WIDTH // 2, PLAY_AREA_HEIGHT // 2 + 50)))
        elif self.state == "victory":
            title = self.font_large.render("Победа!", True, (130, 220, 130))
            subtitle = self.font_medium.render("Нажмите Enter — следующий этап", True, (240, 240, 240))
            self.screen.blit(title, title.get_rect(center=(PLAY_AREA_WIDTH // 2, PLAY_AREA_HEIGHT // 2 - 40)))
            self.screen.blit(subtitle, subtitle.get_rect(center=(PLAY_AREA_WIDTH // 2, PLAY_AREA_HEIGHT // 2 + 20)))

    def draw(self) -> None:
        self.screen.fill(BG_COLOR)
        play_surface = self.screen.subsurface(pygame.Rect(0, 0, PLAY_AREA_WIDTH, PLAY_AREA_HEIGHT))
        play_surface.fill((28, 32, 44))
        self.level.draw(play_surface)
        for bullet in self.bullets:
            bullet.draw(play_surface)
        if self.player.active:
            self.player.draw(play_surface)
        for enemy in self.enemies:
            enemy.draw(play_surface)
        self.level.draw_overlay(play_surface)
        self.draw_panel()
        self.draw_state_overlay()

    def run(self) -> None:
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            self.handle_events()
            self.update(dt)
            self.draw()
            pygame.display.flip()
        pygame.quit()


def main() -> None:
    Game().run()


if __name__ == "__main__":
    main()
