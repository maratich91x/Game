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
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Iterable, List, Optional, Tuple

import pygame
import math
from array import array

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
BG_COLOR_BOTTOM = (46, 52, 68)
PANEL_BG = (26, 28, 36)
PANEL_BG_BOTTOM = (36, 40, 52)
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


def _clamp_color(value: float) -> int:
    return max(0, min(255, int(value)))


def lighten_color(color: Tuple[int, int, int], amount: float) -> Tuple[int, int, int]:
    return tuple(_clamp_color(c + (255 - c) * amount) for c in color)


def darken_color(color: Tuple[int, int, int], amount: float) -> Tuple[int, int, int]:
    return tuple(_clamp_color(c * (1.0 - amount)) for c in color)

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


class SoundManager:
    def __init__(self) -> None:
        self.available = False
        self.sounds: Dict[str, pygame.mixer.Sound] = {}

    def initialize(self) -> None:
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init(frequency=44100, size=-16, channels=2)
            self.available = True
            self.sounds = {
                "shoot": self._generate_tone(1280, 0.08, 0.35),
                "shoot_enemy": self._generate_tone(820, 0.08, 0.3),
                "impact": self._generate_tone(480, 0.12, 0.4),
                "brick": self._generate_tone(360, 0.18, 0.5),
                "explosion": self._generate_noise(0.25, 0.4),
                "bonus_spawn": self._generate_tone(980, 0.18, 0.4),
                "bonus_pick": self._generate_tone(1320, 0.22, 0.45),
                "ricochet": self._generate_tone(720, 0.12, 0.35),
            }
        except pygame.error:
            self.available = False

    def play(self, name: str) -> None:
        if not self.available:
            return
        sound = self.sounds.get(name)
        if sound is not None:
            sound.play()

    @staticmethod
    def _generate_tone(frequency: float, duration: float, volume: float) -> pygame.mixer.Sound:
        sample_rate = 44100
        n_samples = int(sample_rate * duration)
        amplitude = int(volume * 32767)
        buffer = array("h")
        for i in range(n_samples):
            sample = int(amplitude * math.sin(2.0 * math.pi * frequency * (i / sample_rate)))
            buffer.append(sample)
            buffer.append(sample)
        return pygame.mixer.Sound(buffer=buffer.tobytes())

    @staticmethod
    def _generate_noise(duration: float, volume: float) -> pygame.mixer.Sound:
        sample_rate = 44100
        n_samples = int(sample_rate * duration)
        amplitude = int(volume * 32767)
        buffer = array("h")
        random_value = random.random
        for _ in range(n_samples):
            sample = int(amplitude * (random_value() * 2.0 - 1.0))
            buffer.append(sample)
            buffer.append(sample)
        return pygame.mixer.Sound(buffer=buffer.tobytes())


class ImpactEffect:
    def __init__(self, position: Tuple[float, float], color: Tuple[int, int, int], radius: float = 16.0, duration: float = 0.35, thickness: int = 3):
        self.position = pygame.Vector2(position)
        self.color = color
        self.radius = radius
        self.duration = duration
        self.thickness = thickness
        self.elapsed = 0.0

    def update(self, dt: float) -> None:
        self.elapsed += dt

    def draw(self, surface: pygame.Surface) -> None:
        progress = min(1.0, self.elapsed / self.duration) if self.duration > 0 else 1.0
        current_radius = max(2, int(self.radius * (0.3 + 0.7 * progress)))
        alpha = max(0, min(255, int(220 * (1.0 - progress))))
        circle_surface = pygame.Surface((current_radius * 2, current_radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(circle_surface, (*self.color, alpha), (current_radius, current_radius), current_radius, self.thickness)
        surface.blit(circle_surface, circle_surface.get_rect(center=(int(self.position.x), int(self.position.y))))

    @property
    def finished(self) -> bool:
        return self.elapsed >= self.duration


class BonusType(Enum):
    SHIELD = "shield"
    RAPID_FIRE = "rapid_fire"
    SPEED = "speed"
    EXTRA_LIFE = "extra_life"


@dataclass(frozen=True)
class BonusDefinition:
    color: Tuple[int, int, int]
    glow: Tuple[int, int, int]
    border: Tuple[int, int, int]
    icon: str


BONUS_DEFINITIONS: Dict[BonusType, BonusDefinition] = {
    BonusType.SHIELD: BonusDefinition((100, 200, 255), (50, 140, 230), (200, 240, 255), "shield"),
    BonusType.RAPID_FIRE: BonusDefinition((255, 210, 110), (255, 150, 70), (255, 240, 190), "bolt"),
    BonusType.SPEED: BonusDefinition((170, 220, 120), (100, 180, 90), (220, 255, 200), "wing"),
    BonusType.EXTRA_LIFE: BonusDefinition((240, 120, 150), (200, 70, 100), (255, 200, 210), "heart"),
}


class Bonus:
    SIZE = TILE_SIZE - 6

    def __init__(self, bonus_type: BonusType, position: Tuple[float, float]):
        self.type = bonus_type
        self.position = pygame.Vector2(position)
        self.rect = pygame.Rect(0, 0, self.SIZE, self.SIZE)
        self.rect.center = (int(self.position.x), int(self.position.y))
        self.timer = 14.0
        self.pulse = 0.0

    def update(self, dt: float) -> None:
        self.timer -= dt
        self.pulse += dt * 4.0

    @property
    def expired(self) -> bool:
        return self.timer <= 0.0

    def draw(self, surface: pygame.Surface) -> None:
        definition = BONUS_DEFINITIONS[self.type]
        pulse_scale = 1.0 + 0.08 * math.sin(self.pulse)
        draw_width = int(self.rect.width * pulse_scale)
        draw_height = int(self.rect.height * pulse_scale)
        draw_rect = pygame.Rect(0, 0, draw_width, draw_height)
        draw_rect.center = self.rect.center
        glow_radius = max(draw_rect.width, draw_rect.height) + 10
        glow_surface = pygame.Surface((glow_radius, glow_radius), pygame.SRCALPHA)
        pygame.draw.circle(
            glow_surface,
            (*definition.glow, 80),
            (glow_radius // 2, glow_radius // 2),
            glow_radius // 2,
        )
        surface.blit(glow_surface, glow_surface.get_rect(center=draw_rect.center))
        pygame.draw.rect(surface, definition.color, draw_rect, border_radius=8)
        pygame.draw.rect(surface, definition.border, draw_rect, 2, border_radius=8)
        icon_rect = draw_rect.inflate(-10, -10)
        if definition.icon == "shield":
            top = (icon_rect.centerx, icon_rect.top)
            left = (icon_rect.left, icon_rect.centery)
            right = (icon_rect.right, icon_rect.centery)
            bottom = (icon_rect.centerx, icon_rect.bottom)
            pygame.draw.polygon(surface, definition.border, [top, right, bottom, left])
        elif definition.icon == "bolt":
            points = [
                (icon_rect.centerx - 6, icon_rect.top),
                (icon_rect.centerx + 2, icon_rect.centery - 4),
                (icon_rect.centerx - 4, icon_rect.centery - 2),
                (icon_rect.centerx + 6, icon_rect.bottom),
                (icon_rect.centerx - 2, icon_rect.centery + 2),
                (icon_rect.centerx + 4, icon_rect.centery + 4),
            ]
            pygame.draw.polygon(surface, definition.border, points)
        elif definition.icon == "wing":
            pygame.draw.ellipse(surface, definition.border, icon_rect)
            wing_rect = icon_rect.inflate(-icon_rect.width // 4, -icon_rect.height // 3)
            pygame.draw.ellipse(surface, definition.color, wing_rect)
        elif definition.icon == "heart":
            radius = icon_rect.width // 4
            center_left = (icon_rect.left + radius, icon_rect.top + radius)
            center_right = (icon_rect.right - radius, icon_rect.top + radius)
            bottom_point = (icon_rect.centerx, icon_rect.bottom)
            pygame.draw.circle(surface, definition.border, center_left, radius)
            pygame.draw.circle(surface, definition.border, center_right, radius)
            pygame.draw.polygon(surface, definition.border, [
                (icon_rect.left, icon_rect.top + radius),
                bottom_point,
                (icon_rect.right, icon_rect.top + radius),
            ])


class TileArtCache:
    _cache: Dict[TileType, pygame.Surface] = {}

    @classmethod
    def get_surface(cls, tile_type: TileType) -> pygame.Surface:
        surface = cls._cache.get(tile_type)
        if surface is None:
            surface = cls._create_surface(tile_type)
            cls._cache[tile_type] = surface
        return surface

    @classmethod
    def _create_surface(cls, tile_type: TileType) -> pygame.Surface:
        surface = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
        definition = TILE_DEFINITIONS[tile_type]
        rect = surface.get_rect()
        base_color = definition.color
        if tile_type == TileType.BRICK:
            pygame.draw.rect(surface, darken_color(base_color, 0.1), rect)
            inner = rect.inflate(-4, -4)
            pygame.draw.rect(surface, lighten_color(base_color, 0.2), inner)
            mortar = darken_color(base_color, 0.35)
            step_y = TILE_SIZE // 4
            for i in range(1, 4):
                pygame.draw.line(surface, mortar, (0, i * step_y), (TILE_SIZE, i * step_y), 1)
            pygame.draw.line(surface, mortar, (TILE_SIZE // 2, 0), (TILE_SIZE // 2, TILE_SIZE), 1)
        elif tile_type == TileType.STEEL:
            pygame.draw.rect(surface, darken_color(base_color, 0.3), rect, border_radius=4)
            inner = rect.inflate(-4, -4)
            pygame.draw.rect(surface, lighten_color(base_color, 0.3), inner, border_radius=3)
            pygame.draw.line(surface, darken_color(base_color, 0.45), inner.topleft, inner.bottomleft, 2)
            pygame.draw.line(surface, lighten_color(base_color, 0.45), inner.topright, inner.bottomright, 2)
            pygame.draw.line(surface, lighten_color(base_color, 0.3), inner.midtop, inner.midbottom, 2)
            pygame.draw.line(surface, darken_color(base_color, 0.4), inner.midleft, inner.midright, 2)
        elif tile_type == TileType.WATER:
            surface.fill((0, 0, 0, 0))
            pygame.draw.rect(surface, (*base_color, 220), rect, border_radius=6)
            wave_color = lighten_color(base_color, 0.4)
            for offset in range(3):
                arc_rect = rect.inflate(-6, -6).move(0, offset * 3)
                pygame.draw.arc(surface, wave_color, arc_rect, 0.6 + offset * 0.35, 2.7 + offset * 0.35, 2)
        elif tile_type == TileType.FOREST:
            surface.fill((0, 0, 0, 0))
            pygame.draw.rect(surface, (*darken_color(base_color, 0.2), 210), rect, border_radius=6)
            leaf_color = (*lighten_color(base_color, 0.3), 240)
            highlight_color = (*lighten_color(base_color, 0.45), 230)
            for dx, dy in ((6, 6), (18, 8), (12, 16), (6, 18), (16, 18), (10, 12)):
                pygame.draw.circle(surface, leaf_color, (dx, dy), 4)
            pygame.draw.circle(surface, highlight_color, (rect.centerx, rect.centery - 4), 5)
        elif tile_type == TileType.ICE:
            pygame.draw.rect(surface, lighten_color(base_color, 0.1), rect, border_radius=4)
            inner = rect.inflate(-5, -5)
            pygame.draw.rect(surface, lighten_color(base_color, 0.35), inner, border_radius=4)
            pygame.draw.line(surface, (255, 255, 255), inner.topleft, inner.bottomright, 1)
            pygame.draw.line(surface, (200, 220, 255), inner.topright, inner.bottomleft, 1)
        elif tile_type == TileType.BASE:
            pygame.draw.rect(surface, lighten_color(base_color, 0.1), rect, border_radius=4)
            inner = rect.inflate(-6, -6)
            pygame.draw.rect(surface, base_color, inner, border_radius=3)
            star_points = [
                (inner.centerx, inner.top + 2),
                (inner.centerx + 6, inner.centery - 2),
                (inner.right - 2, inner.centery),
                (inner.centerx + 6, inner.centery + 2),
                (inner.centerx, inner.bottom - 2),
                (inner.centerx - 6, inner.centery + 2),
                (inner.left + 2, inner.centery),
                (inner.centerx - 6, inner.centery - 2),
            ]
            pygame.draw.polygon(surface, darken_color(base_color, 0.25), star_points)
        elif tile_type == TileType.BASE_RUIN:
            pygame.draw.rect(surface, base_color, rect)
            crack = darken_color(base_color, 0.35)
            pygame.draw.line(surface, crack, rect.topleft, rect.bottomright, 3)
            pygame.draw.line(surface, crack, rect.topright, rect.bottomleft, 3)
        else:
            pygame.draw.rect(surface, base_color, rect)
        return surface


@dataclass
class Tile:
    grid_x: int
    grid_y: int
    definition: TileDefinition
    rect: pygame.Rect
    surface: pygame.Surface = field(init=False)

    def set_definition(self, definition: TileDefinition) -> None:
        self.definition = definition
        self.surface = TileArtCache.get_surface(definition.tile_type)

    def __post_init__(self) -> None:
        self.surface = TileArtCache.get_surface(self.definition.tile_type)


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
            surface.blit(tile.surface, tile.rect)

    def draw_overlay(self, surface: pygame.Surface) -> None:
        for tile in self.overlay_tiles:
            surface.blit(tile.surface, tile.rect)


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
        glow_rect = self.rect.inflate(6, 6)
        glow_surface = pygame.Surface(glow_rect.size, pygame.SRCALPHA)
        pygame.draw.ellipse(glow_surface, (*lighten_color(BULLET_COLOR, 0.25), 80), glow_surface.get_rect())
        surface.blit(glow_surface, glow_rect.topleft)
        pygame.draw.rect(surface, BULLET_COLOR, self.rect, border_radius=3)
        inner = self.rect.inflate(-2, -2)
        if inner.width > 0 and inner.height > 0:
            pygame.draw.rect(surface, lighten_color(BULLET_COLOR, 0.35), inner, border_radius=2)
        pygame.draw.rect(surface, darken_color(BULLET_COLOR, 0.5), self.rect, 1, border_radius=3)


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
        if self.invulnerable_timer > 0 and int(self.invulnerable_timer * 6) % 2 == 0:
            base_color = lighten_color(self.color, 0.4)
        highlight = lighten_color(base_color, 0.25)
        shadow = darken_color(base_color, 0.45)
        body_rect = self.rect
        track_width = max(4, body_rect.width // 5)
        left_track = pygame.Rect(body_rect.left, body_rect.top + 1, track_width, body_rect.height - 2)
        right_track = pygame.Rect(body_rect.right - track_width, body_rect.top + 1, track_width, body_rect.height - 2)
        pygame.draw.rect(surface, shadow, left_track, border_radius=2)
        pygame.draw.rect(surface, shadow, right_track, border_radius=2)
        center_rect = body_rect.inflate(-track_width * 2 + 2, -4)
        pygame.draw.rect(surface, base_color, center_rect, border_radius=4)
        pygame.draw.rect(surface, highlight, center_rect.inflate(-4, -4), border_radius=3)
        pygame.draw.rect(surface, darken_color(base_color, 0.3), center_rect, 2, border_radius=4)
        turret_rect = center_rect.inflate(-6, -6)
        if turret_rect.width > 0 and turret_rect.height > 0:
            pygame.draw.rect(surface, darken_color(base_color, 0.2), turret_rect, border_radius=3)
            pygame.draw.rect(surface, highlight, turret_rect.inflate(-3, -3), border_radius=2)
        barrel_start = pygame.Vector2(body_rect.center)
        barrel_length = body_rect.width // 2 + 6
        barrel_end = barrel_start + self.direction.vector * barrel_length
        pygame.draw.line(surface, shadow, barrel_start, barrel_end, 6)
        pygame.draw.line(surface, lighten_color(base_color, 0.4), barrel_start, barrel_end, 2)


class PlayerTank(Tank):
    def __init__(self, x: float, y: float):
        super().__init__(x, y, PLAYER_COLOR, PLAYER_SPEED, PLAYER_FIRE_DELAY, PLAYER_BULLET_SPEED, True)
        self.spawn_point = pygame.Vector2(x, y)
        self.base_speed = self.speed
        self.base_fire_delay = self.fire_delay
        self.base_bullet_speed = self.bullet_speed
        self.rapid_fire_duration = 8.0
        self.speed_boost_duration = 6.0
        self.rapid_fire_timer = 0.0
        self.speed_boost_timer = 0.0
        self.lives = PLAYER_LIVES
        self.active = True
        self.dead = False
        self.respawn_delay = 1.6
        self.respawn_timer = 0.0

    def reset_modifiers(self) -> None:
        self.speed = self.base_speed
        self.fire_delay = self.base_fire_delay
        self.bullet_speed = self.base_bullet_speed
        self.max_bullets = 1
        self.rapid_fire_timer = 0.0
        self.speed_boost_timer = 0.0

    def update_powerups(self, dt: float) -> None:
        if self.rapid_fire_timer > 0:
            self.rapid_fire_timer = max(0.0, self.rapid_fire_timer - dt)
            if self.rapid_fire_timer <= 0.0:
                self.fire_delay = self.base_fire_delay
                self.bullet_speed = self.base_bullet_speed
                self.max_bullets = 1
        if self.speed_boost_timer > 0:
            self.speed_boost_timer = max(0.0, self.speed_boost_timer - dt)
            if self.speed_boost_timer <= 0.0:
                self.speed = self.base_speed

    def apply_bonus(self, bonus_type: BonusType) -> str:
        if bonus_type == BonusType.SHIELD:
            self.invulnerable_timer = max(self.invulnerable_timer, 8.0)
            return "Энергетический щит"
        if bonus_type == BonusType.RAPID_FIRE:
            self.rapid_fire_timer = self.rapid_fire_duration
            self.fire_delay = max(0.18, self.base_fire_delay * 0.55)
            self.bullet_speed = self.base_bullet_speed * 1.35
            self.max_bullets = 2
            return "Скорострельность"
        if bonus_type == BonusType.SPEED:
            self.speed_boost_timer = self.speed_boost_duration
            self.speed = self.base_speed * 1.3
            return "Турбо"
        if bonus_type == BonusType.EXTRA_LIFE:
            self.lives += 1
            return "+1 жизнь"
        return ""

    def reset_position(self, x: float, y: float) -> None:
        self.spawn_point.update(x, y)
        self.pos.update(x, y)
        self.rect.topleft = (int(x), int(y))
        self.direction = Direction.UP
        self.cooldown_timer = 0.0
        self.invulnerable_timer = 2.0
        self.active_bullets = 0
        self.reset_modifiers()
        self.active = True
        self.dead = False
        self.respawn_timer = 0.0

    def start_respawn(self) -> None:
        self.dead = True
        self.active = False
        self.respawn_timer = self.respawn_delay
        self.invulnerable_timer = 0.0
        self.reset_modifiers()

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
        if self.invulnerable_timer > 0:
            glow_radius = self.rect.width + 12
            glow_surface = pygame.Surface((glow_radius, glow_radius), pygame.SRCALPHA)
            alpha = 90 + int(40 * math.sin(pygame.time.get_ticks() / 140))
            pygame.draw.circle(glow_surface, (120, 220, 255, alpha), (glow_radius // 2, glow_radius // 2), glow_radius // 2)
            surface.blit(glow_surface, glow_surface.get_rect(center=self.rect.center))
        super().draw(surface)
        if self.rapid_fire_timer > 0:
            spark_rect = self.rect.inflate(-self.rect.width // 2, -self.rect.height // 2)
            pygame.draw.rect(surface, (255, 210, 120), spark_rect, 2, border_radius=4)
            pygame.draw.rect(surface, (255, 240, 200), spark_rect.inflate(-4, -4), 1, border_radius=3)
        if self.speed_boost_timer > 0:
            trail_color = (180, 255, 160, 140)
            for offset in (-8, -4, 0):
                trail_rect = pygame.Rect(self.rect.left - 6, self.rect.top + 6 + offset, 6, 4)
                trail_surface = pygame.Surface(trail_rect.size, pygame.SRCALPHA)
                pygame.draw.rect(trail_surface, trail_color, trail_surface.get_rect(), border_radius=2)
                surface.blit(trail_surface, trail_rect.topleft)


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
        self.sound_manager = SoundManager()
        self.sound_manager.initialize()
        self.running = True
        self.state = "menu"
        self.stage = 1
        self.score = 0
        self.playfield_background = self._create_playfield_background()
        self.playfield_overlay = self._create_playfield_overlay()
        self.panel_background = self._create_panel_background()
        self.level = Level(parse_level_layout(LEVEL_LAYOUT))
        self.player = PlayerTank(TILE_SIZE * 12, TILE_SIZE * 23)
        self.player.active = False
        self.enemies: List[EnemyTank] = []
        self.bullets: List[Bullet] = []
        self.effects: List[ImpactEffect] = []
        self.bonuses: List[Bonus] = []
        self.remaining_enemies = 0
        self.enemy_spawn_timer = 0.0
        self.game_over_reason: Optional[str] = None
        self.bonus_message: Optional[str] = None
        self.bonus_message_timer = 0.0

    def _create_playfield_background(self) -> pygame.Surface:
        surface = pygame.Surface((PLAY_AREA_WIDTH, PLAY_AREA_HEIGHT))
        for y in range(PLAY_AREA_HEIGHT):
            t = y / max(1, PLAY_AREA_HEIGHT - 1)
            color = tuple(
                int(BG_COLOR[i] * (1.0 - t) + BG_COLOR_BOTTOM[i] * t) for i in range(3)
            )
            pygame.draw.line(surface, color, (0, y), (PLAY_AREA_WIDTH, y))
        return surface

    def _create_playfield_overlay(self) -> pygame.Surface:
        surface = pygame.Surface((PLAY_AREA_WIDTH, PLAY_AREA_HEIGHT), pygame.SRCALPHA)
        line_color = (20, 24, 36, 55)
        for x in range(0, PLAY_AREA_WIDTH, TILE_SIZE):
            pygame.draw.line(surface, line_color, (x, 0), (x, PLAY_AREA_HEIGHT))
        for y in range(0, PLAY_AREA_HEIGHT, TILE_SIZE):
            pygame.draw.line(surface, (18, 22, 30, 45), (0, y), (PLAY_AREA_WIDTH, y))
        return surface

    def _create_panel_background(self) -> pygame.Surface:
        surface = pygame.Surface((PANEL_WIDTH, SCREEN_HEIGHT))
        for y in range(SCREEN_HEIGHT):
            t = y / max(1, SCREEN_HEIGHT - 1)
            color = tuple(
                int(PANEL_BG[i] * (1.0 - t) + PANEL_BG_BOTTOM[i] * t) for i in range(3)
            )
            pygame.draw.line(surface, color, (0, y), (PANEL_WIDTH, y))
        return surface

    def start_new_game(self) -> None:
        self.stage = 1
        self.score = 0
        self.player = PlayerTank(TILE_SIZE * 12, TILE_SIZE * 23)
        self.effects.clear()
        self.bonuses.clear()
        self.bullets.clear()
        self.bonus_message = None
        self.bonus_message_timer = 0.0
        self.prepare_stage(reset_lives=True)

    def prepare_stage(self, reset_lives: bool = False) -> None:
        self.level = Level(parse_level_layout(LEVEL_LAYOUT))
        self.enemies.clear()
        self.bullets.clear()
        self.effects.clear()
        self.bonuses.clear()
        base_count = ENEMY_BASE_COUNT + (self.stage - 1) * ENEMY_PER_STAGE
        self.remaining_enemies = min(base_count, MAX_TOTAL_ENEMIES)
        self.enemy_spawn_timer = 2.0
        if reset_lives:
            self.player.lives = PLAYER_LIVES
        self.player.reset_position(TILE_SIZE * 12, TILE_SIZE * 23)
        self.player.invulnerable_timer = 2.5
        self.state = "playing"
        self.game_over_reason = None
        self.bonus_message = None
        self.bonus_message_timer = 0.0

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
                self.on_bullet_fired(bullet)

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
                if collision == "brick":
                    self.sound_manager.play("brick")
                    self.add_effect(bullet.rect.center, (255, 170, 120), radius=18.0)
                elif collision == "block":
                    self.sound_manager.play("impact")
                    self.add_effect(bullet.rect.center, (180, 200, 220), radius=14.0)
                elif collision == "base" and self.state == "playing":
                    self.sound_manager.play("explosion")
                    self.add_effect(bullet.rect.center, (255, 120, 120), radius=26.0)
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
                        self.sound_manager.play("explosion")
                        self.add_effect(target_hit.rect.center, (255, 200, 120), radius=28.0)
                        self.try_spawn_bonus(target_hit.rect.center)
                    else:
                        self.sound_manager.play("impact")
                        self.add_effect(target_hit.rect.center, (255, 200, 120), radius=18.0)
                    self.remove_bullet(bullet)
                    continue
            else:
                if self.player.active and self.player.invulnerable_timer <= 0 and bullet.rect.colliderect(self.player.rect):
                    self.sound_manager.play("explosion")
                    self.add_effect(self.player.rect.center, (255, 140, 120), radius=28.0)
                    self.remove_bullet(bullet)
                    self.on_player_hit()
                    continue
            # проверка столкновений пуль между собой
        to_remove: List[Bullet] = []
        collision_points: List[Tuple[float, float]] = []
        for i, bullet_a in enumerate(self.bullets):
            for bullet_b in self.bullets[i + 1 :]:
                if bullet_a.friendly == bullet_b.friendly:
                    continue
                if bullet_a.rect.colliderect(bullet_b.rect):
                    if bullet_a not in to_remove:
                        to_remove.append(bullet_a)
                    if bullet_b not in to_remove:
                        to_remove.append(bullet_b)
                    collision_points.append(
                        (
                            (bullet_a.rect.centerx + bullet_b.rect.centerx) / 2,
                            (bullet_a.rect.centery + bullet_b.rect.centery) / 2,
                        )
                    )
        if collision_points:
            self.sound_manager.play("ricochet")
        for bullet in to_remove:
            self.remove_bullet(bullet)
        for point in collision_points:
            self.add_effect(point, (255, 240, 200), radius=16.0, duration=0.28, thickness=2)

    def remove_bullet(self, bullet: Bullet) -> None:
        if bullet in self.bullets:
            self.bullets.remove(bullet)
            bullet.owner.on_bullet_destroyed()

    def add_effect(
        self,
        position: Tuple[float, float],
        color: Tuple[int, int, int],
        radius: float = 16.0,
        duration: float = 0.35,
        thickness: int = 3,
    ) -> None:
        self.effects.append(ImpactEffect(position, color, radius, duration, thickness))

    def update_effects(self, dt: float) -> None:
        for effect in list(self.effects):
            effect.update(dt)
            if effect.finished:
                self.effects.remove(effect)

    def on_bullet_fired(self, bullet: Bullet) -> None:
        color = (255, 220, 140) if bullet.friendly else (255, 140, 110)
        self.add_effect(bullet.rect.center, color, radius=12.0, duration=0.18, thickness=2)
        self.sound_manager.play("shoot" if bullet.friendly else "shoot_enemy")

    def try_spawn_bonus(self, position: Tuple[int, int]) -> None:
        if len(self.bonuses) >= 3:
            return
        if random.random() > 0.25:
            return
        bonus_type = random.choices(
            [BonusType.SHIELD, BonusType.RAPID_FIRE, BonusType.SPEED, BonusType.EXTRA_LIFE],
            weights=[0.28, 0.28, 0.22, 0.22],
        )[0]
        spawn_x = max(Bonus.SIZE // 2, min(PLAY_AREA_WIDTH - Bonus.SIZE // 2, position[0]))
        spawn_y = max(Bonus.SIZE // 2, min(PLAY_AREA_HEIGHT - Bonus.SIZE // 2, position[1]))
        bonus = Bonus(bonus_type, (spawn_x, spawn_y))
        self.bonuses.append(bonus)
        definition = BONUS_DEFINITIONS[bonus_type]
        self.sound_manager.play("bonus_spawn")
        self.add_effect((spawn_x, spawn_y), definition.color, radius=24.0, duration=0.45, thickness=4)

    def update_bonuses(self, dt: float) -> None:
        for bonus in list(self.bonuses):
            bonus.update(dt)
            if bonus.expired:
                self.bonuses.remove(bonus)
                continue
            if self.player.active and self.player.rect.colliderect(bonus.rect):
                message = self.player.apply_bonus(bonus.type)
                self.bonuses.remove(bonus)
                self.sound_manager.play("bonus_pick")
                definition = BONUS_DEFINITIONS[bonus.type]
                self.add_effect(bonus.rect.center, definition.color, radius=26.0, duration=0.4, thickness=4)
                if message:
                    self.show_bonus_message(message)

    def show_bonus_message(self, text: str) -> None:
        self.bonus_message = text
        self.bonus_message_timer = 3.0

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
        if self.bonus_message_timer > 0:
            self.bonus_message_timer = max(0.0, self.bonus_message_timer - dt)
            if self.bonus_message_timer <= 0.0:
                self.bonus_message = None
        if self.state != "playing":
            self.update_effects(dt)
            return
        self.player.update_timers(dt)
        self.player.update_powerups(dt)
        if self.player.dead:
            self.player.update_respawn(dt, self.level, self.enemies)
        else:
            self.handle_player_input(dt)
        for enemy in list(self.enemies):
            bullet = enemy.update_ai(dt, self.level, self.player, self.enemies)
            if bullet is not None:
                self.bullets.append(bullet)
                self.on_bullet_fired(bullet)
        self.update_bullets(dt)
        self.update_bonuses(dt)
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
        self.update_effects(dt)

    def draw_panel(self) -> None:
        panel_rect = pygame.Rect(PLAY_AREA_WIDTH, 0, PANEL_WIDTH, SCREEN_HEIGHT)
        self.screen.blit(self.panel_background, panel_rect)
        pygame.draw.rect(self.screen, PANEL_ACCENT, panel_rect, 2, border_radius=8)
        lines = [
            f"Этап: {self.stage}",
            f"Очки: {self.score}",
            f"Жизни: {self.player.lives}",
            f"Враги: {self.remaining_enemies + len(self.enemies)}",
        ]
        text_y = 24
        for line in lines:
            text = self.font_medium.render(line, True, PANEL_TEXT)
            self.screen.blit(text, (PLAY_AREA_WIDTH + 16, text_y))
            text_y += 36
        status_y = text_y + 12
        if self.player.invulnerable_timer > 0:
            shield_progress = min(1.0, self.player.invulnerable_timer / 8.0)
            status_y = self._draw_status_bar("Щит", shield_progress, status_y, (120, 210, 255))
        if self.player.rapid_fire_timer > 0:
            progress = self.player.rapid_fire_timer / self.player.rapid_fire_duration if self.player.rapid_fire_duration > 0 else 0
            status_y = self._draw_status_bar("Скорострельность", progress, status_y, (255, 210, 130))
        if self.player.speed_boost_timer > 0:
            progress = self.player.speed_boost_timer / self.player.speed_boost_duration if self.player.speed_boost_duration > 0 else 0
            status_y = self._draw_status_bar("Скорость", progress, status_y, (170, 220, 130))
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
        if self.bonus_message:
            message_surface = self.font_small.render(self.bonus_message, True, PANEL_ACCENT)
            self.screen.blit(message_surface, (PLAY_AREA_WIDTH + 16, SCREEN_HEIGHT - 72))

    def _draw_status_bar(self, label: str, progress: float, y: int, color: Tuple[int, int, int]) -> int:
        text = self.font_small.render(label, True, PANEL_TEXT)
        self.screen.blit(text, (PLAY_AREA_WIDTH + 16, y))
        bar_rect = pygame.Rect(PLAY_AREA_WIDTH + 16, y + 18, PANEL_WIDTH - 32, 10)
        pygame.draw.rect(self.screen, (34, 40, 56), bar_rect, border_radius=4)
        inner = bar_rect.inflate(-2, -2)
        inner.width = int(inner.width * max(0.0, min(1.0, progress)))
        pygame.draw.rect(self.screen, color, inner, border_radius=4)
        return y + 32

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
        self.screen.blit(self.playfield_background, (0, 0))
        play_surface = self.screen.subsurface(pygame.Rect(0, 0, PLAY_AREA_WIDTH, PLAY_AREA_HEIGHT))
        play_surface.blit(self.playfield_overlay, (0, 0))
        self.level.draw(play_surface)
        for bonus in self.bonuses:
            bonus.draw(play_surface)
        for bullet in self.bullets:
            bullet.draw(play_surface)
        if self.player.active:
            self.player.draw(play_surface)
        for enemy in self.enemies:
            enemy.draw(play_surface)
        self.level.draw_overlay(play_surface)
        for effect in self.effects:
            effect.draw(play_surface)
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
