
# -*- coding: utf-8 -*-
"""
Vanosik vs Pizdyuk — Office Saga (Deluxe Roguelike)
Дата: 2025-08-09

Что нового:
- Сеттинг офиса: комнаты связаны дверями (коридор-хаб + кабинеты, кухня, серверная, склад)
- Поиск Пиздюка по уликам (✉ записки) и таймер его переезда между комнатами
- Бой с сохранением "Делюкс"-графики, частиц, комбо, XP и УЛЬТы
- Миникарта (правый верх) + журнал улик (TAB)
- Интро-предыстория при запуске с кинематографическими слайдами

Управление:
  WASD — движение
  SPACE — удар
  SHIFT — ульта (когда готова)
  E — действие (двери/улики)
  TAB — журнал улик
  F11 — полноэкран
  ESC — выход
"""

# --- Auto-install pygame if missing ---
try:
    import pygame  # noqa
except ModuleNotFoundError:
    import sys, subprocess
    print("Pygame not found. Installing...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pygame", "--quiet"])
    except Exception as e:
        print("Auto-install failed:", e)
        print("Install manually:  python -m pip install pygame")
        raise
    import pygame  # noqa

import sys, random, math, os, wave, struct, time, json, datetime
from pygame import Vector2

# ====== GAME SETTINGS ======
WIDTH, HEIGHT = 1024, 640
FPS = 60

# Combat / RPG (из "Deluxe")
BASE_PIZDYUK_HP = 120
DAMAGE_PER_HIT_BASE = 12
KNOCKBACK_PIX_BASE = 28
HP_GROWTH = 0.35
SPD_GROWTH = 0.10
BASE_POINTS = 10
XP_PER_HIT = 6
XP_PER_LEVEL_CLEAR = 60
XP_LEVEL_BASE = 100
XP_LEVEL_GROW = 1.25
RAGE_PER_HIT = 14
RAGE_MAX = 100
ULT_COOLDOWN = 5.0
ULT_DAMAGE = 45
ULT_RADIUS = 130
ULT_KNOCKBACK = 110

# Boss
BOSS_HP_MULT = 2.2
BOSS_SPD_MULT = 1.25
BOSS_KB_RESIST = 0.6
BOSS_COLOR = (255, 90, 40)

# Office roguelike
MOVE_DELAY = 42.0       # через сколько сек Пиздюк переезжает
NOTE_SPAWN_CHANCE = 0.85
ROOM_W, ROOM_H = WIDTH, HEIGHT

# Colors
UI_TEXT = (28, 30, 38)
UI_MUTE = (90, 95, 110)
OK_CLR = (108, 198, 132)
HP_BG = (230, 100, 100)
HP_FG = (80, 220, 110)
COMBO_CLR = (255, 180, 60)
LEVEL_CLR = (96, 140, 236)
VANOSIK_CLR = (64, 140, 255)
PIZDYUK_CLR = (255, 138, 40)
PIZDYUK_HIT_CLR = (255, 80, 80)
BG_TOP = (28, 32, 58)
BG_BOTTOM = (13, 15, 26)
GLOW_CLR = (255, 140, 80, 140)

# Fonts
def load_fonts():
    return (
        pygame.font.SysFont("Arial", 18, bold=True),
        pygame.font.SysFont("Arial", 24, bold=True),
        pygame.font.SysFont("Arial", 32, bold=True),
        pygame.font.SysFont("Arial", 48, bold=True),
    )

# ====== SOUND GENERATION ======
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SND_DIR = os.path.join(BASE_DIR, "snd"); os.makedirs(SND_DIR, exist_ok=True)

def gen_tone_wav(path, freq=440, ms=80, volume=0.5, fade_ms=8, sample_rate=44100):
    if os.path.exists(path): return path
    frames = int(sample_rate * ms / 1000.0)
    fade = int(sample_rate * fade_ms / 1000.0)
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        for i in range(frames):
            amp = volume
            if i < fade: amp *= i / max(1, fade)
            if i > frames - fade: amp *= (frames - i) / max(1, fade)
            val = int(amp * 32767.0 * math.sin(2 * math.pi * freq * (i / sample_rate)))
            wf.writeframesraw(struct.pack("<h", val))
    return path

def gen_cry_wav(path):
    if os.path.exists(path): return path
    sample_rate = 44100
    total_ms = 280
    f1, f2 = 520, 340
    frames = int(sample_rate * total_ms / 1000.0)
    with wave.open(path, "w") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sample_rate)
        for i in range(frames):
            t = i / sample_rate
            s = 0.5*math.sin(2*math.pi*f1*t) + 0.5*math.sin(2*math.pi*f2*t + 0.6*math.sin(30*t))
            env = 1.0
            if i < 400: env *= i/400
            if i > frames-800: env *= (frames - i)/800
            val = int(0.65 * env * 32767.0 * s)
            wf.writeframesraw(struct.pack("<h", val))
    return path

HIT_WAV  = gen_tone_wav(os.path.join(SND_DIR, "hit.wav"),   freq=220, ms=90,  volume=0.7)
STEP_WAV = gen_tone_wav(os.path.join(SND_DIR, "step.wav"),  freq=420, ms=40,  volume=0.3)
WIN_WAV  = gen_tone_wav(os.path.join(SND_DIR, "win.wav"),   freq=720, ms=180, volume=0.6)
LOSE_WAV = gen_tone_wav(os.path.join(SND_DIR, "lose.wav"),  freq=180, ms=220, volume=0.6)
LEVEL_WAV= gen_tone_wav(os.path.join(SND_DIR, "lvl.wav"),   freq=520, ms=140, volume=0.6)
CRY_WAV  = gen_cry_wav(os.path.join(SND_DIR, "cry.wav"))

# ====== PYGAME INIT ======
try:
    pygame.mixer.pre_init(44100, -16, 1, 512)
except Exception:
    pass
pygame.init()
try:
    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.SCALED, vsync=1)
except TypeError:
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Vanosik vs Pizdyuk — Office Saga")
clock = pygame.time.Clock()

try:
    pygame.mixer.init()
except Exception:
    pass

try:
    snd_hit  = pygame.mixer.Sound(HIT_WAV)
    snd_step = pygame.mixer.Sound(STEP_WAV)
    snd_win  = pygame.mixer.Sound(WIN_WAV)
    snd_lose = pygame.mixer.Sound(LOSE_WAV)
    snd_lvl  = pygame.mixer.Sound(LEVEL_WAV)
    snd_cry  = pygame.mixer.Sound(CRY_WAV)
    snd_step.set_volume(0.35)
except Exception:
    snd_hit = snd_step = snd_win = snd_lose = snd_lvl = snd_cry = None

font_small, font_mid, font_big, font_huge = load_fonts()

# ====== UTIL VISUALS ======
def draw_vertical_gradient(surface, top_color, bottom_color):
    h = surface.get_height()
    for y in range(h):
        t = y / (h-1)
        r = int(top_color[0]*(1-t) + bottom_color[0]*t)
        g = int(top_color[1]*(1-t) + bottom_color[1]*t)
        b = int(top_color[2]*(1-t) + bottom_color[2]*t)
        pygame.draw.line(surface, (r,g,b), (0,y), (surface.get_width(), y))

def draw_glow(surface, pos, radius, color=(255,140,80,120)):
    x, y = pos
    layers = 8
    for i in range(layers, 0, -1):
        a = int(color[3] * (i/layers)**2)
        r = int(radius * (i/layers))
        s = pygame.Surface((r*2, r*2), pygame.SRCALPHA)
        pygame.draw.circle(s, (color[0], color[1], color[2], a), (r, r), r)
        surface.blit(s, (x-r, y-r), special_flags=pygame.BLEND_PREMULTIPLIED)

def draw_rounded_rect(surface, rect, color, radius=10):
    pygame.draw.rect(surface, color, rect, border_radius=radius)

def text_with_outline(text, font, main=(255,255,255), outline=(0,0,0), shift=1):
    base = font.render(text, True, main)
    w, h = base.get_width()+shift*2, base.get_height()+shift*2
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    for dx,dy in ((-shift,0),(shift,0),(0,-shift),(0,shift),(-shift,-shift),(shift,shift),(-shift,shift),(shift,-shift)):
        surf.blit(font.render(text, True, outline), (dx+shift, dy+shift))
    surf.blit(base, (shift, shift))
    return surf

# ====== PARTICLES ======
class Particle:
    def __init__(self, pos, vel, life, size, color):
        self.x, self.y = pos
        self.vx, self.vy = vel
        self.life = life
        self.life_max = life
        self.size = size
        self.color = color

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += 300 * dt  # gravity
        self.life -= dt
        return self.life > 0

    def render(self, surface):
        t = max(0.0, min(1.0, self.life/self.life_max))
        a = int(220 * t)
        s = max(1, int(self.size * (0.6 + 0.4*t)))
        c = (*self.color[:3], a)
        temp = pygame.Surface((s*2, s*2), pygame.SRCALPHA)
        pygame.draw.circle(temp, c, (s, s), s)
        surface.blit(temp, (int(self.x)-s, int(self.y)-s), special_flags=pygame.BLEND_PREMULTIPLIED)

class ParticleSystem:
    def __init__(self):
        self.items = []

    def spawn_hit(self, pos, base_color=(255,180,60)):
        for _ in range(12):
            ang = random.random()*math.tau
            spd = random.uniform(120, 280)
            vx, vy = math.cos(ang)*spd, math.sin(ang)*spd
            life = random.uniform(0.25, 0.5)
            size = random.randint(2, 4)
            c = (base_color[0], base_color[1], base_color[2])
            self.items.append(Particle(pos, (vx,vy), life, size, c))

    def spawn_ult_ring(self, pos, color=(255,120,60)):
        for _ in range(36):
            ang = (_/36.0)*math.tau
            spd = random.uniform(260, 380)
            vx, vy = math.cos(ang)*spd, math.sin(ang)*spd
            life = random.uniform(0.35, 0.6)
            size = random.randint(2, 3)
            self.items.append(Particle(pos, (vx,vy), life, size, color))

    def update(self, dt):
        self.items = [p for p in self.items if p.update(dt)]

    def render(self, surface):
        for p in self.items:
            p.render(surface)

# ====== SIMPLE RPG SYSTEMS ======
# Эти классы минимально расширяют оригинальную игру, добавляя
# инвентарь, навыки и квесты. Реализация остаётся базовой и
# служит заготовкой для дальнейшего развития.

class Item:
    """Простой предмет инвентаря."""
    def __init__(self, name, itype="misc", damage=0, speed=0):
        self.name = name
        self.type = itype
        self.damage = damage
        self.speed = speed


class Inventory:
    def __init__(self):
        self.items = []
        self.equipped = {}

    def add(self, item: Item):
        self.items.append(item)

    def equip(self, item: Item):
        self.equipped[item.type] = item

    def bonus_damage(self):
        return sum(i.damage for i in self.equipped.values())

    def bonus_speed(self):
        return sum(i.speed for i in self.equipped.values())


class Skill:
    def __init__(self, name, cost=1):
        self.name = name
        self.cost = cost
        self.unlocked = False


class SkillTree:
    def __init__(self):
        self.skills = {
            "damage": Skill("Урон", cost=1),
            "speed": Skill("Скорость", cost=1),
            "cooldown": Skill("Перезарядка", cost=1),
            "range": Skill("Дальность", cost=1),
        }

    def unlock(self, key, player):
        sk = self.skills.get(key)
        if sk and not sk.unlocked and player.skill_points >= sk.cost:
            sk.unlocked = True
            player.skill_points -= sk.cost
            if key == "damage":
                player.damage_bonus += 1
            elif key == "speed":
                player.speed_bonus += 1; player.recompute_stats()
            elif key == "cooldown":
                player.cd_bonus += 1.0
            elif key == "range":
                player.range_bonus += 1


class Quest:
    def __init__(self, desc):
        self.desc = desc
        self.completed = False


class Dialogue:
    def __init__(self, lines):
        self.lines = lines
        self.idx = 0

    def current(self):
        if self.idx < len(self.lines):
            return self.lines[self.idx]
        return ""

    def next(self):
        if self.idx < len(self.lines) - 1:
            self.idx += 1
            return True
        return False

# ====== SAVE / LOAD ======
SAVE_PATH = os.path.join(BASE_DIR, "save.json")


def save_game(game):
    data = {
        "level": game.player.level,
        "xp": game.player.xp,
        "xp_next": game.player.xp_next,
        "skill_points": game.player.skill_points,
        "damage_bonus": game.player.damage_bonus,
        "speed_bonus": game.player.speed_bonus,
        "cd_bonus": game.player.cd_bonus,
        "range_bonus": game.player.range_bonus,
        "inventory": [i.__dict__ for i in game.player.inventory.items],
        "equipped": {k: v.__dict__ for k, v in game.player.inventory.equipped.items()},
        "current_room": game.current_room,
        "score": game.score,
        "notes": game.notes_log,
    }
    with open(SAVE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_game(game):
    if not os.path.exists(SAVE_PATH):
        return False
    with open(SAVE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    p = game.player
    p.level = data.get("level", 1)
    p.xp = data.get("xp", 0)
    p.xp_next = data.get("xp_next", XP_LEVEL_BASE)
    p.skill_points = data.get("skill_points", 0)
    p.damage_bonus = data.get("damage_bonus", 0)
    p.speed_bonus = data.get("speed_bonus", 0)
    p.cd_bonus = data.get("cd_bonus", 0.0)
    p.range_bonus = data.get("range_bonus", 0)
    p.inventory.items = [Item(**d) for d in data.get("inventory", [])]
    p.inventory.equipped = {k: Item(**v) for k, v in data.get("equipped", {}).items()}
    p.recompute_stats()
    game.current_room = data.get("current_room", "Коридор")
    game.score = data.get("score", 0)
    game.notes_log = data.get("notes", [])
    game.scene = game.build_room(game.current_room)
    return True


class MainMenu:
    """Простейшее главное меню."""
    def __init__(self):
        self.options = ["Играть", "Выход"]
        self.idx = 0

    def update(self, events):
        for e in events:
            if e.type == pygame.KEYDOWN:
                if e.key in (pygame.K_DOWN, pygame.K_s):
                    self.idx = (self.idx + 1) % len(self.options)
                elif e.key in (pygame.K_UP, pygame.K_w):
                    self.idx = (self.idx - 1) % len(self.options)
                elif e.key in (pygame.K_RETURN, pygame.K_SPACE):
                    return self.options[self.idx]
        return None

    def draw(self, surf):
        surf.fill((20, 22, 30))
        title = text_with_outline("Vanosik Office Saga", font_huge, (240,240,255), (0,0,0))
        surf.blit(title, (WIDTH//2 - title.get_width()//2, 120))
        for i, opt in enumerate(self.options):
            col = (255,255,255) if i == self.idx else (150,150,150)
            r = text_with_outline(opt, font_big, col, (0,0,0))
            surf.blit(r, (WIDTH//2 - r.get_width()//2, 260 + i*60))

# ====== CHARACTERS (Deluxe visuals) ======
class Vanosik(pygame.sprite.Sprite):
    def __init__(self, pos):
        super().__init__()
        self.w, self.h = 58, 74
        self.images = self._build_anim_surfaces(VANOSIK_CLR)
        self.state = "idle"
        self.anim_t = 0.0
        self.anim_idx = 0
        self.image = self.images[self.state][self.anim_idx]
        self.rect = self.image.get_rect(center=pos)
        self.base_speed = 270.0
        self.speed = self.base_speed
        self.dir = pygame.Vector2(1, 0)
        self.attack_cooldown = 0.0
        self.attack_cd_total = 0.45
        self.attack_time = 0.2
        self.attacking_t = 0.0
        self.last_step_t = 0.0
        self._hit_registered = False

        # RPG
        self.level = 1
        self.xp = 0
        self.xp_next = XP_LEVEL_BASE
        self.skill_points = 0
        self.damage_bonus = 0
        self.speed_bonus = 0
        self.cd_bonus = 0.0
        self.range_bonus = 0

        # Rage
        self.rage = 0
        self.ult_cd = 0.0

        # Новые системы
        self.inventory = Inventory()
        self.skills = SkillTree()
        self.recompute_stats()

    def recompute_stats(self):
        """Учитывает бонусы от инвентаря."""
        self.speed = self.base_speed + 14 * self.speed_bonus + self.inventory.bonus_speed()

    def _char_surface(self, body_color, shadow=True, punch=False, phase=0.0):
        surf = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        if shadow:
            sh = pygame.Surface((self.w, 20), pygame.SRCALPHA)
            pygame.draw.ellipse(sh, (0,0,0,80), (8,0,self.w-16,14))
            surf.blit(sh, (0, self.h-18), special_flags=pygame.BLEND_PREMULTIPLIED)
        outline = (20,30,60)
        cx = self.w//2
        leg_off = int(math.sin(phase)*6)
        pygame.draw.rect(surf, outline, (cx-14, 42+leg_off, 12, 18), border_radius=6)
        pygame.draw.rect(surf, outline, (cx+2,  42-leg_off, 12, 18), border_radius=6)
        pygame.draw.rect(surf, body_color, (cx-13, 43+leg_off, 10, 16), border_radius=6)
        pygame.draw.rect(surf, body_color, (cx+3,  43-leg_off, 10, 16), border_radius=6)
        pygame.draw.rect(surf, outline, (cx-12, 18, 24, 30), border_radius=8)
        pygame.draw.rect(surf, body_color, (cx-11, 19, 22, 28), border_radius=8)
        shade = pygame.Surface((22,28), pygame.SRCALPHA)
        draw_vertical_gradient(shade, (255,255,255,90), (0,0,0,0))
        surf.blit(shade, (cx-11,19), special_flags=pygame.BLEND_PREMULTIPLIED)
        pygame.draw.circle(surf, outline, (cx, 12), 10)
        pygame.draw.circle(surf, body_color, (cx, 12), 9)
        if punch:
            pygame.draw.rect(surf, outline, (cx+8, 24, 20, 10), border_radius=6)
            pygame.draw.rect(surf, body_color, (cx+9, 25, 18, 8), border_radius=6)
            pygame.draw.rect(surf, outline, (cx-16, 24, 10, 16), border_radius=6)
            pygame.draw.rect(surf, body_color, (cx-15, 25, 8, 14), border_radius=6)
        else:
            arm_off = int(math.cos(phase)*6)
            for dx in (-16, 14):
                pygame.draw.rect(surf, outline, (cx+dx, 24 + (arm_off if dx<0 else -arm_off), 10, 16), border_radius=6)
                pygame.draw.rect(surf, body_color, (cx+dx+1, 25 + (arm_off if dx<0 else -arm_off), 8, 14), border_radius=6)
        return surf

    def _build_anim_surfaces(self, base_color):
        path = os.path.join(BASE_DIR, "assets", "vanosik.png")
        if os.path.exists(path):
            img = pygame.image.load(path).convert_alpha()
            return {"idle": [img], "walk": [img], "attack": [img]}
        idle = [ self._char_surface(base_color, punch=False, phase=0.0),
                 self._char_surface(base_color, punch=False, phase=1.1) ]
        walk = [ self._char_surface(base_color, punch=False, phase=p) for p in (0.0,0.9,1.8,2.7) ]
        attack = [ self._char_surface(base_color, punch=True,  phase=0.0),
                   self._char_surface(base_color, punch=True,  phase=0.6) ]
        return {"idle": idle, "walk": walk, "attack": attack}

    def _set_state(self, st):
        if st != self.state:
            self.state = st; self.anim_idx = 0; self.anim_t = 0.0
            frames = self.images[self.state]
            self.image = frames[0] if frames else self.image

    def update(self, dt, keys):
        if self.ult_cd > 0: self.ult_cd = max(0.0, self.ult_cd - dt)
        self.recompute_stats()
        vel = pygame.Vector2(0, 0)
        if keys[pygame.K_w]: vel.y -= 1
        if keys[pygame.K_s]: vel.y += 1
        if keys[pygame.K_a]: vel.x -= 1
        if keys[pygame.K_d]: vel.x += 1
        if vel.length_squared() > 0:
            vel = vel.normalize() * self.speed
            self.dir = (vel.normalize() if vel.length() else pygame.Vector2(1, 0))
            if self.state != "attack": self._set_state("walk")
        else:
            if self.state != "attack": self._set_state("idle")
        self.rect.x += int(vel.x * dt); self.rect.y += int(vel.y * dt)
        self.rect.x = max(0, min(WIDTH - self.rect.w, self.rect.x))
        self.rect.y = max(80, min(HEIGHT - self.rect.h, self.rect.y))

        self.anim_t += dt
        frame_rate = 0.12 if self.state == "walk" else (0.08 if self.state == "attack" else 0.4)
        frames = self.images[self.state]
        if frames:
            if self.anim_t >= frame_rate:
                self.anim_t = 0.0; self.anim_idx = (self.anim_idx + 1) % len(frames)
            img = frames[self.anim_idx]
            if self.dir.x < -0.2: img = pygame.transform.flip(img, True, False)
            self.image = img

        if self.attack_cooldown > 0: self.attack_cooldown = max(0.0, self.attack_cooldown - dt)
        if self.state == "walk" and snd_step:
            self.last_step_t += dt
            if self.last_step_t >= 0.22:
                self.last_step_t = 0.0
                try: snd_step.play()
                except: pass

        if self.attacking():
            self.attacking_t -= dt
            if self.attacking_t <= 0:
                self._set_state("idle"); self._hit_registered = False

    def can_attack(self):
        return self.attack_cooldown <= 0.0 and not self.attacking()

    def start_attack(self):
        self._set_state("attack")
        self.attacking_t = self.attack_time
        self.attack_cd_total = max(0.18, 0.45 - 0.05*self.cd_bonus)
        self.attack_cooldown = self.attack_cd_total
        self._hit_registered = False

    def attacking(self):
        return self.state == "attack" and self.attacking_t > 0.0

    def get_attack_hitbox(self):
        d = self.dir if self.dir.length_squared() > 0 else pygame.Vector2(1, 0)
        base_w, base_h = 28, 24
        extra = 6 * self.range_bonus
        w, h = base_w + extra, base_h + extra//2
        cx, cy = self.rect.center
        if abs(d.x) >= abs(d.y):
            return pygame.Rect(cx + (12 if d.x>=0 else -12 - w), cy - h//2, w, h)
        else:
            return pygame.Rect(cx - h//2, cy + (12 if d.y>=0 else -12 - w), h, w)

    def add_xp(self, amount):
        self.xp += amount
        leveled = False
        while self.xp >= self.xp_next:
            self.xp -= self.xp_next
            self.level += 1
            self.skill_points += 1
            self.xp_next = int(self.xp_next * XP_LEVEL_GROW)
            leveled = True
        return leveled

    def try_ult(self):
        return self.rage >= RAGE_MAX and self.ult_cd <= 0.0

class Pizdyuk(pygame.sprite.Sprite):
    def __init__(self, pos, boss=False):
        super().__init__()
        self.is_boss = boss
        self.w, self.h = (64, 80) if boss else (50, 62)
        base = BOSS_COLOR if boss else PIZDYUK_CLR
        self.images = self._build_anim_surfaces(base, (255,120,160) if boss else PIZDYUK_HIT_CLR)
        self.state = "run"
        self.anim_t = 0.0; self.anim_idx = 0
        self.image = self.images[self.state][self.anim_idx]
        self.rect = self.image.get_rect(center=pos)
        self.base_speed = 210.0 * (BOSS_SPD_MULT if boss else 1.0)
        self.speed = self.base_speed
        self.dir = pygame.Vector2(-1, 0)
        self.hit_t = 0.0
        self.taunt_timer = random.uniform(1.2, 2.4)
        self.last_phrase = ""
        self.cry_timer = 0.0
        self.orbit_sign = random.choice([-1, 1])
        self.hp_max = int(BASE_PIZDYUK_HP * (BOSS_HP_MULT if boss else 1.0))
        self.hp = self.hp_max

    def _char_surface(self, base, hitc, hurt=False, phase=0.0):
        surf = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        sh = pygame.Surface((self.w, 22), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0,0,0,80), (8,0,self.w-16,16))
        surf.blit(sh, (0, self.h-20), special_flags=pygame.BLEND_PREMULTIPLIED)
        outline = (35, 24, 48) if self.is_boss else (24, 20, 36)
        body = hitc if hurt else base
        cx = self.w//2
        leg_off = int(math.sin(phase) * (8 if self.is_boss else 6))
        pygame.draw.rect(surf, outline, (cx-10, 44+leg_off, 10, 16), border_radius=6)
        pygame.draw.rect(surf, outline, (cx+2,  44-leg_off, 10, 16), border_radius=6)
        pygame.draw.rect(surf, body, (cx-9, 45+leg_off, 8, 14), border_radius=6)
        pygame.draw.rect(surf, body, (cx+3, 45-leg_off, 8, 14), border_radius=6)
        pygame.draw.rect(surf, outline, (cx-12, 18, 24, 28), border_radius=10)
        pygame.draw.rect(surf, body, (cx-11, 19, 22, 26), border_radius=10)
        shade = pygame.Surface((22,26), pygame.SRCALPHA)
        draw_vertical_gradient(shade, (255,255,255,80), (0,0,0,0))
        surf.blit(shade, (cx-11,19), special_flags=pygame.BLEND_PREMULTIPLIED)
        pygame.draw.circle(surf, outline, (cx,12), 10 if self.is_boss else 9)
        pygame.draw.circle(surf, body, (cx,12), 9 if self.is_boss else 8)
        arm_off = int(math.cos(phase) * (6 if self.is_boss else 5))
        for dx in (-16, 14):
            pygame.draw.rect(surf, outline, (cx+dx, 22 + (arm_off if dx<0 else -arm_off), 10, 14), border_radius=6)
            pygame.draw.rect(surf, body, (cx+dx+1, 23 + (arm_off if dx<0 else -arm_off), 8, 12), border_radius=6)
        return surf

    def _build_anim_surfaces(self, base, hitc):
        path = os.path.join(BASE_DIR, "assets", "pizdyuk.png")
        if os.path.exists(path):
            img = pygame.image.load(path).convert_alpha()
            return {"run": [img], "hit": [img]}
        run = [ self._char_surface(base, hitc, hurt=False, phase=p) for p in (0.0,1.1,2.2,3.3) ]
        hit = [ self._char_surface(base, hitc, hurt=True,  phase=p) for p in (0.0,1.2) ]
        return {"run": run, "hit": hit}

    def _set_state(self, st):
        if st != self.state:
            self.state = st; self.anim_idx = 0; self.anim_t = 0.0
            frames = self.images[self.state]
            self.image = frames[0] if frames else self.image

    def update(self, dt, player_rect):
        if self.state == "hit":
            self.hit_t -= dt
            if self.hit_t <= 0: self._set_state("run")
        to_player = pygame.Vector2(player_rect.center) - pygame.Vector2(self.rect.center)
        dist = to_player.length() + 1e-6
        dir_to = to_player.normalize()
        desired_min, desired_max = (140, 260) if not self.is_boss else (160, 300)
        if dist < desired_min: base_vec = -dir_to
        elif dist > desired_max: base_vec = dir_to * 0.6
        else: base_vec = pygame.Vector2(0, 0)
        tangent = pygame.Vector2(-dir_to.y, dir_to.x) * self.orbit_sign
        jitter = pygame.Vector2(random.uniform(-0.3, 0.3), random.uniform(-0.3, 0.3))
        charge = pygame.Vector2(0, 0)
        if random.random() < (0.02 if not self.is_boss else 0.04):
            charge = (dir_to if dist > desired_max else -dir_to) * (2.0 if not self.is_boss else 2.6)

        w_base = 1.4 if dist < desired_min else (0.5 if dist > desired_max else 0.0)
        self.dir = base_vec * w_base + tangent * 1.0 + jitter * 0.6 + charge * 1.4
        if self.dir.length_squared() > 0: self.dir = self.dir.normalize()
        vel = self.dir * self.speed
        self.rect.x += int(vel.x * dt); self.rect.y += int(vel.y * dt)
        self.rect.x = max(0, min(WIDTH - self.rect.w, self.rect.x))
        self.rect.y = max(80, min(HEIGHT - self.rect.h, self.rect.y))

        self.anim_t += dt
        frames = self.images[self.state]
        if frames:
            frame_rate = 0.10 if self.state == "run" else 0.06
            if self.anim_t >= frame_rate:
                self.anim_t = 0.0; self.anim_idx = (self.anim_idx + 1) % len(frames)
            img = frames[self.anim_idx]
            if self.dir.x < -0.2: img = pygame.transform.flip(img, True, False)
            self.image = img

        if self.cry_timer > 0: self.cry_timer -= dt
        else:
            self.taunt_timer -= dt
            if self.taunt_timer <= 0:
                if dist > 120:
                    self.last_phrase = random.choice(["Сдавайся, динозавр!","Ты слишком медленный!","Мой перерыв важнее!"])
                    self.taunt_timer = random.uniform(2.2, 4.0)
                else:
                    self.taunt_timer = random.uniform(1.2, 2.2)

    def on_hit(self, knockback_vec):
        self._set_state("hit"); self.hit_t = 0.25
        kb = knockback_vec * (BOSS_KB_RESIST if self.is_boss else 1.0)
        self.rect.x += int(kb.x); self.rect.y += int(kb.y)
        self.rect.x = max(0, min(WIDTH - self.rect.w, self.rect.x))
        self.rect.y = max(80, min(HEIGHT - self.rect.h, self.rect.y))
        self.last_phrase = random.choice(["ААА! Больно!","Не бей!","Ай! За что?!"]); self.cry_timer = 0.6
        if snd_cry:
            try: snd_cry.play()
            except: pass

# ====== Office map ======
ROOMS = {
    "Коридор":           ["Кухня", "Комната охраны", "Кабинет директора", "Серверная"],
    "Кухня":             ["Коридор", "Склад техники", "Переговорная"],
    "Склад техники":     ["Кухня", "Кабинет менеджеров"],
    "Комната охраны":    ["Коридор", "Кабинет зама №1"],
    "Серверная":         ["Коридор", "Кабинет айтишника", "Кабинет зама №2"],
    "Переговорная":      ["Кухня", "Кабинет директора"],
    "Кабинет директора": ["Переговорная", "Коридор"],
    "Кабинет менеджеров":["Склад техники", "Кабинет зама №2"],
    "Кабинет зама №1":   ["Комната охраны", "Кабинет менеджеров"],
    "Кабинет зама №2":   ["Серверная", "Кабинет менеджеров"],
    "Кабинет айтишника": ["Серверная"],
}

ROOM_COLORS = {
    "Коридор": (32, 34, 42),
    "Кухня": (35, 48, 38),
    "Склад техники": (40, 36, 30),
    "Комната охраны": (33, 38, 44),
    "Серверная": (29, 33, 53),
    "Переговорная": (38, 35, 44),
    "Кабинет директора": (44, 32, 32),
    "Кабинет менеджеров": (37, 37, 32),
    "Кабинет зама №1": (33, 41, 41),
    "Кабинет зама №2": (41, 33, 41),
    "Кабинет айтишника": (28, 40, 48),
}

NOTE_TEMPLATES = [
    "Этот динозавтр Иван, не понимает, что отдых — святое. Пойду в {room}.",
    "Скажу, что на совещании. На деле — {room}.",
    "Где тихо? Правильно, {room}. Там и посплю.",
    "Если что, скажу — Ваносик просил проверить принтер у {room}.",
    "Идеальное убежище — {room}. Никто не найдёт!",
]

class Door:
    def __init__(self, rect, target_room, label):
        self.rect = pygame.Rect(rect)
        self.target = target_room
        self.label = label

    def draw(self, surf):
        pygame.draw.rect(surf, (180,180,220), self.rect, 2)
        txt = text_with_outline(f"→ {self.target}", font_small, (230,230,240), (0,0,0))
        surf.blit(txt, (self.rect.x+6, self.rect.y+6))

class Note:
    def __init__(self, pos, text):
        self.pos = Vector2(pos)
        self.text = text
        self.rect = pygame.Rect(int(pos[0]-10), int(pos[1]-8), 20, 16)
        self.picked = False

    def draw(self, surf):
        if self.picked: return
        pygame.draw.rect(surf, (250,240,180), self.rect)
        pygame.draw.rect(surf, (80,60,20), self.rect, 2)
        surf.blit(font_small.render("✉", True, (60,40,10)), (self.rect.x+3, self.rect.y-2))

class RoomScene:
    def __init__(self, name):
        self.name = name
        self.doors = []
        self.notes = []

    def make_default_doors(self):
        neighbors = ROOMS[self.name]
        slots = [(WIDTH-200, HEIGHT//2-40, 180, 80),  # right
                 (20, HEIGHT//2-40, 180, 80),         # left
                 (WIDTH//2-90, 70, 180, 60),          # top
                 (WIDTH//2-90, HEIGHT-110, 180, 60)]  # bottom
        self.doors.clear()
        for i, nb in enumerate(neighbors[:4]):
            self.doors.append(Door(slots[i], nb, f"В {nb}"))

    def draw_bg(self, surf):
        path = os.path.join(BASE_DIR, "assets", "rooms", f"{self.name}.png")
        if os.path.exists(path):
            img = pygame.image.load(path).convert()
            surf.blit(img, (0,0))
        else:
            base = ROOM_COLORS.get(self.name, (36,36,42))
            surf.fill(base)
        # header strip
        pygame.draw.rect(surf, (0,0,0,120), (0,0,WIDTH,60))
        title = text_with_outline(self.name, font_big, (240,240,255), (0,0,0))
        surf.blit(title, (24, 14))
        hint = font_small.render("E — действие   TAB — журнал   SPACE — удар   SHIFT — ульта", True, (210,210,230))
        surf.blit(hint, (24, 40))

    def draw(self, surf):
        self.draw_bg(surf)
        # subtle grid like Deluxe
        grid = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        step = 48
        for y in range(60, HEIGHT, step):
            a = 28 if (y//step) % 2 == 0 else 16
            pygame.draw.line(grid, (255,255,255,a), (0,y), (WIDTH,y))
        for x in range(0, WIDTH, step):
            a = 28 if (x//step) % 2 == 0 else 16
            pygame.draw.line(grid, (255,255,255,a), (x,60), (x,HEIGHT))
        surf.blit(grid, (0,0))
        for d in self.doors: d.draw(surf)
        for n in self.notes: n.draw(surf)

# ====== UI (HUD, карта, журнал) ======
def hud_panel(surf, rect, alpha=140):
    panel = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    panel.fill((0,0,0,alpha))
    surf.blit(panel, rect)

def draw_hp_bar_above(surface, sprite_rect, hp, hp_max, is_boss=False):
    ratio = max(0.0, min(1.0, hp / max(1, hp_max)))
    w, h = (120, 14) if is_boss else (70, 10)
    x = sprite_rect.centerx - w // 2
    y = sprite_rect.top - (22 if is_boss else 14)
    pygame.draw.rect(surface, (255,255,255,30), (x-2,y-2,w+4,h+4), border_radius=8)
    pygame.draw.rect(surface, (32,36,48), (x,y,w,h), border_radius=8)
    grad = pygame.Surface((w, h), pygame.SRCALPHA)
    for yy in range(h):
        t = yy/max(1,h-1)
        cr = int(HP_BG[0]*(1-t) + HP_FG[0]*t)
        cg = int(HP_BG[1]*(1-t) + HP_FG[1]*t)
        cb = int(HP_BG[2]*(1-t) + HP_FG[2]*t)
        pygame.draw.line(grad, (cr,cg,cb,220), (0,yy), (int(w*ratio), yy))
    surface.blit(grad, (x,y))

def draw_minimap(surf, current_room, piz_room):
    map_rect = pygame.Rect(WIDTH-280, 12, 268, 220)
    hud_panel(surf, map_rect)
    surf.blit(font_small.render("Карта", True, (230,230,240)), (map_rect.x+8, map_rect.y+6))
    rooms = list(ROOMS.keys()); cols = 3
    spacing_x, spacing_y = 80, 60
    start_x, start_y = map_rect.x+24, map_rect.y+34
    positions = {}
    for idx, r in enumerate(rooms):
        cx = idx % cols; cy = idx // cols
        x = start_x + cx * spacing_x; y = start_y + cy * spacing_y
        positions[r] = (x,y)
    for r, ns in ROOMS.items():
        x,y = positions[r]
        for nb in ns:
            nx, ny = positions[nb]
            pygame.draw.line(surf, (130,130,150), (x,y), (nx,ny), 1)
    for r, (x,y) in positions.items():
        col = (130,130,150)
        if r == current_room: col = (240,240,80)
        elif r == piz_room: col = (220,90,90)
        pygame.draw.circle(surf, col, (x,y), 7)
        surf.blit(font_small.render(str(rooms.index(r)+1), True, (230,230,240)), (x-5,y-10))

def draw_notes_log(surf, notes_log):
    rect = pygame.Rect(WIDTH//2-360, 90, 720, HEIGHT-180)
    hud_panel(surf, rect)
    title = text_with_outline("Журнал улик (TAB)", font_big, (240,240,255), (0,0,0))
    surf.blit(title, (rect.x+16, rect.y+12))
    y = rect.y + 60
    if not notes_log:
        surf.blit(font_mid.render("Пока нет улик. Ищи записки ✉ в комнатах.", True, (220,220,230)), (rect.x+16, y))
    else:
        for i, t in enumerate(notes_log[-12:]):
            txt = font_small.render("• " + t, True, (230,230,240))
            surf.blit(txt, (rect.x+16, y))
            y += 26

def draw_rage_bar(surface, player):
    label = text_with_outline("Rage", font_small, (245,240,255), (0,0,0))
    surface.blit(label, (16, HEIGHT - 74))
    bar_w, bar_h = 180, 12; x, y = 16, HEIGHT - 44
    draw_rounded_rect(surface, (x,y,bar_w,bar_h), (20,22,36), 6)
    w = int(bar_w * max(0, min(1, player.rage/RAGE_MAX)))
    draw_rounded_rect(surface, (x,y,w,bar_h), (220,120,60), 6)
    if player.ult_cd > 0:
        cd_txt = font_small.render(f"ULT КД: {player.ult_cd:.1f}s", True, UI_MUTE)
        surface.blit(cd_txt, (x + bar_w + 12, y - 2))

def draw_xp_bar(surface, player):
    txt = text_with_outline(f"Лвл игрока: {player.level}  (SP: {player.skill_points})", font_small, (240,245,255), (0,0,0))
    surface.blit(txt, (WIDTH - txt.get_width() - 16, HEIGHT - 74))
    bar_w, bar_h = 220, 12; x, y = WIDTH - bar_w - 16, HEIGHT - 44
    draw_rounded_rect(surface, (x,y,bar_w,bar_h), (20,22,36), 6)
    ratio = player.xp / max(1, player.xp_next)
    draw_rounded_rect(surface, (x,y,int(bar_w*ratio),bar_h), (120,160,240), 6)
    hint = font_small.render("1:Урон  2:Скорость  3:-КД  4:Дальность", True, UI_MUTE)
    surface.blit(hint, (x, y - 18))


def draw_inventory(surface, inv):
    rect = pygame.Rect(WIDTH//2-200, HEIGHT//2-150, 400, 300)
    hud_panel(surface, rect)
    title = text_with_outline("Инвентарь (I)", font_big, (240,240,255), (0,0,0))
    surface.blit(title, (rect.x+16, rect.y+12))
    y = rect.y + 60
    if not inv.items:
        surface.blit(font_mid.render("Пусто", True, (220,220,230)), (rect.x+16, y))
    else:
        for it in inv.items:
            surface.blit(font_small.render(f"{it.name}", True, (230,230,240)), (rect.x+16, y))
            y += 24


def draw_skill_tree(surface, tree):
    rect = pygame.Rect(WIDTH//2-200, HEIGHT//2-150, 400, 300)
    hud_panel(surface, rect)
    title = text_with_outline("Навыки (K)", font_big, (240,240,255), (0,0,0))
    surface.blit(title, (rect.x+16, rect.y+12))
    y = rect.y + 60
    for i, (k, sk) in enumerate(tree.skills.items(), 1):
        status = "✓" if sk.unlocked else f"{i}"
        txt = font_small.render(f"[{status}] {sk.name}", True, (230,230,240))
        surface.blit(txt, (rect.x+16, y)); y += 26

# ====== Story / Intro ======
INTRO_TEXT = [
    "У Ваносика появился помощник — Пиздюк.",
    "Сначала Ваносик обрадовался: наконец-то помощь!",
    "Но быстро понял: Пиздюк ничего не хочет делать...",
    "Он всё время где-то проябывается и косит от работы.",
    "Ваносик терпел, терпел...",
    "Но терпению пришёл КОНЕЦ.",
    "Ваносик пошёл искать Пиздюка, чтобы его ОТПИЗДИТЬ!!!"
]

def show_intro():
    tbg = pygame.Surface((WIDTH, HEIGHT)); draw_vertical_gradient(tbg, BG_TOP, BG_BOTTOM)
    vignette = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    for r in range(10, max(WIDTH,HEIGHT)//2, 4):
        alpha = int(220 * (r/(max(WIDTH,HEIGHT)//2))**2)
        pygame.draw.circle(vignette, (0,0,0,alpha//10), (WIDTH//2, HEIGHT//2), r)
    idx = 0; wait = 0.0
    typing = ""
    last_time = time.perf_counter()
    while True:
        now = time.perf_counter(); dt = min(0.05, now - last_time); last_time = now
        for e in pygame.event.get():
            if e.type == pygame.QUIT: pygame.quit(); sys.exit(0)
            if e.type == pygame.KEYDOWN:
                if e.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                    return
        screen.blit(tbg, (0,0)); screen.blit(vignette, (0,0))
        title = text_with_outline("Vanosik vs Pizduk — Office Saga", font_huge, (255,255,255), (0,0,0))
        screen.blit(title, (WIDTH//2 - title.get_width()//2, 50))

        if idx < len(INTRO_TEXT):
            wait -= dt
            if wait <= 0:
                full = INTRO_TEXT[idx]
                # typing effect
                if len(typing) < len(full):
                    typing = full[:len(typing)+1]
                else:
                    idx += 1; typing = ""; wait = 0.3
        y = 170
        for i in range(min(idx, len(INTRO_TEXT))):
            s = text_with_outline(INTRO_TEXT[i], font_big, (240,240,255), (0,0,0))
            screen.blit(s, (WIDTH//2 - s.get_width()//2, y)); y += 44
        if idx < len(INTRO_TEXT):
            s = text_with_outline(typing, font_big, (255,220,120), (0,0,0))
            screen.blit(s, (WIDTH//2 - s.get_width()//2, y))

        tip = font_small.render("Нажми ENTER/SPACE — начать", True, (230,230,240))
        screen.blit(tip, (WIDTH//2 - tip.get_width()//2, HEIGHT-40))

        pygame.display.flip(); clock.tick(60)

# ====== GAME STATE (explore/combat) ======
class Game:
    def __init__(self):
        self.reset()

    def reset(self):
        self.state = "explore"    # explore | combat
        self.player = Vanosik((WIDTH//2, HEIGHT//2+60))
        self.current_room = "Коридор"
        self.scene = self.build_room(self.current_room)
        self.notes_log = []
        self.piz_room = random.choice(list(ROOMS.keys()))
        self.piz = None
        self.piz_move_t = MOVE_DELAY
        self.score = 0
        self.fullscreen = False
        self.tab_open = False
        self.inv_open = False
        self.skill_open = False
        self.toast = ""
        self.toast_t = 0.0
        self.round = 1
        self.quests = []
        self.dialogue = None
        sword = Item("Степлер-меч", "weapon", damage=2)
        self.player.inventory.add(sword)
        self.player.inventory.equip(sword)
        self.player.recompute_stats()
        self.spawn_note_in_room(self.current_room)

    def build_room(self, name):
        sc = RoomScene(name)
        sc.make_default_doors()
        sc.notes = []
        return sc

    def spawn_note_in_room(self, name):
        if name == self.piz_room: return
        if random.random() < NOTE_SPAWN_CHANCE:
            txt = random.choice(NOTE_TEMPLATES).format(room=self.piz_room)
            pos = (random.randint(160, WIDTH-160), random.randint(120, HEIGHT-80))
            if self.current_room == name:
                self.scene.notes.append(Note(pos, txt))

    def toast_show(self, text, t=2.2):
        self.toast, self.toast_t = text, t

    def enter_room(self, name):
        self.current_room = name
        self.scene = self.build_room(name)
        self.spawn_note_in_room(name)
        if name == self.piz_room:
            boss = (self.round % 3 == 0)
            self.piz = Pizdyuk((WIDTH//2, HEIGHT//2-20), boss=boss)
            self.state = "combat"
            self.toast_show("Ты нашёл Пиздюка!" + (" (БОСС)" if boss else ""))

    def change_piz_room(self):
        old = self.piz_room
        choices = [r for r in ROOMS.keys() if r != old]
        self.piz_room = random.choice(choices)
        if old == self.current_room:
            pos = (random.randint(140, WIDTH-140), random.randint(120, HEIGHT-120))
            self.scene.notes.append(Note(pos, f"Меня тут нет! Пойду-ка в {self.piz_room}."))

    def update(self, dt, keys):
        for e in pygame.event.get():
            if e.type == pygame.QUIT: pygame.quit(); sys.exit(0)
            elif e.type == pygame.KEYDOWN:
                if self.state == "dialogue":
                    if e.key in (pygame.K_SPACE, pygame.K_RETURN, pygame.K_e):
                        if not self.dialogue.next():
                            self.state = "explore"; self.dialogue = None
                    continue
                if e.key == pygame.K_ESCAPE: pygame.quit(); sys.exit(0)
                elif e.key == pygame.K_F11:
                    self.fullscreen = not self.fullscreen
                    flags = pygame.FULLSCREEN|pygame.SCALED if self.fullscreen else pygame.SCALED
                    try:
                        pygame.display.set_mode((WIDTH, HEIGHT), flags, vsync=1)
                    except TypeError:
                        pygame.display.set_mode((WIDTH, HEIGHT), flags)
                elif e.key == pygame.K_TAB:
                    self.tab_open = not self.tab_open
                elif e.key == pygame.K_i:
                    self.inv_open = not self.inv_open
                elif e.key == pygame.K_k:
                    self.skill_open = not self.skill_open
                elif e.key == pygame.K_F5:
                    save_game(self); self.toast_show("Сохранено")
                elif e.key == pygame.K_F9:
                    if load_game(self): self.toast_show("Загружено")
                elif e.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
                    if self.player.skill_points > 0:
                        keymap = {pygame.K_1:"damage", pygame.K_2:"speed", pygame.K_3:"cooldown", pygame.K_4:"range"}
                        self.player.skills.unlock(keymap[e.key], self.player)

        if self.state == "dialogue":
            return
        if self.state == "explore":
            self.player.update(dt, keys)
            # взаимодействие — двери/улики
            if keys[pygame.K_e]:
                for d in self.scene.doors:
                    if self.player.rect.colliderect(d.rect):
                        self.enter_room(d.target); break
                for n in self.scene.notes:
                    if not n.picked and self.player.rect.colliderect(n.rect):
                        n.picked = True
                        self.notes_log.append(n.text)
                        self.quests.append(Quest(n.text))
                        self.dialogue = Dialogue([n.text])
                        self.state = "dialogue"
                        self.toast_show("Улика подобрана (TAB — журнал)")
            # переезд Пиздюка
            self.piz_move_t -= dt
            if self.piz_move_t <= 0:
                self.piz_move_t = MOVE_DELAY
                self.change_piz_room()

        elif self.state == "combat":
            self.player.update(dt, keys)
            self.piz.update(dt, self.player.rect)
            # Удар игрока
            if keys[pygame.K_SPACE] and self.player.can_attack():
                self.player.start_attack()
            if self.player.attacking() and not self.player._hit_registered:
                hb = self.player.get_attack_hitbox()
                if hb.colliderect(self.piz.rect):
                    if snd_hit:
                        try: snd_hit.play()
                        except: pass
                    # particles
                    particles.spawn_hit(self.piz.rect.center, (255,200,60))
                    dmg = DAMAGE_PER_HIT_BASE + 2*self.player.damage_bonus + self.player.inventory.bonus_damage()
                    self.piz.hp = max(0, self.piz.hp - dmg)
                    k = Vector2(self.piz.rect.center) - Vector2(self.player.rect.center)
                    k = (k.normalize() if k.length_squared() else Vector2(1,0)) * (KNOCKBACK_PIX_BASE + 6*self.player.damage_bonus)
                    if self.piz.is_boss: k *= BOSS_KB_RESIST
                    self.piz.on_hit(k)
                    self.player._hit_registered = True
                    self.player.attacking_t = 0.0
                    self.player._set_state("idle")
                    self.score += BASE_POINTS
                    leveled = self.player.add_xp(XP_PER_HIT)
                    self.player.rage = min(RAGE_MAX, self.player.rage + RAGE_PER_HIT)
                    if leveled: self.toast_show("Новый уровень! (1..4 — прокачка)", 1.8)
                    if self.piz.hp <= 0:
                        self.round += 1
                        self.player.add_xp(XP_PER_LEVEL_CLEAR)
                        self.state = "explore"; self.piz = None
                        self.change_piz_room(); self.piz_move_t = MOVE_DELAY
                        self.toast_show("Пиздюк повержен! Ищем дальше...")
            # УЛЬТА
            if keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]:
                if self.player.try_ult():
                    self.player.rage = 0; self.player.ult_cd = ULT_COOLDOWN
                    ec = Vector2(self.piz.rect.center); pc = Vector2(self.player.rect.center)
                    if ec.distance_to(pc) <= ULT_RADIUS:
                        dmg = ULT_DAMAGE + 3*self.player.damage_bonus + self.player.inventory.bonus_damage()
                        self.piz.hp = max(0, self.piz.hp - dmg)
                        k = (ec - pc)
                        k = (k.normalize() if k.length_squared() else Vector2(1,0)) * ULT_KNOCKBACK
                        if self.piz.is_boss: k *= BOSS_KB_RESIST
                        self.piz.on_hit(k)
                        self.score += 60
                    flash_overlay.set_alpha(200)
                    particles.spawn_ult_ring(pc, (255,120,60))

        if self.player.ult_cd > 0: self.player.ult_cd = max(0.0, self.player.ult_cd - dt)
        if self.toast_t > 0: self.toast_t -= dt

    def render(self, surf):
        self.scene.draw(surf)
        # Пиздюк в бою
        if self.state == "combat" and self.piz:
            surf.blit(self.piz.image, self.piz.rect)
            draw_hp_bar_above(surf, self.piz.rect, self.piz.hp, self.piz.hp_max, is_boss=self.piz.is_boss)
            if self.piz.last_phrase:
                self.draw_bubble(self.piz.last_phrase, (self.piz.rect.centerx, self.piz.rect.top))
        # Игрок
        surf.blit(self.player.image, self.player.rect)
        # Подсказки E
        if self.state == "explore":
            for d in self.scene.doors:
                if self.player.rect.colliderect(d.rect):
                    s = text_with_outline("E — войти", font_small, (240,240,255), (0,0,0))
                    surf.blit(s, (d.rect.centerx-40, d.rect.y-24))
            for n in self.scene.notes:
                if not n.picked and self.player.rect.colliderect(n.rect):
                    s = text_with_outline("E — прочитать", font_small, (240,240,255), (0,0,0))
                    surf.blit(s, (n.rect.centerx-50, n.rect.y-26))

        # Частицы
        particles.render(surf)

        # HUD
        self.draw_hud(surf)

        # Журнал
        if self.tab_open:
            draw_notes_log(surf, self.notes_log)
        if self.inv_open:
            draw_inventory(surf, self.player.inventory)
        if self.skill_open:
            draw_skill_tree(surf, self.player.skills)
        if self.state == "dialogue" and self.dialogue:
            rect = pygame.Rect(WIDTH//2-300, HEIGHT-180, 600, 140)
            hud_panel(surf, rect)
            surf.blit(font_mid.render(self.dialogue.current(), True, (240,240,255)), (rect.x+16, rect.y+16))

        # Flash
        a = flash_overlay.get_alpha()
        if a and a > 0:
            flash_overlay.set_alpha(max(0, a-12))
            surf.blit(flash_overlay, (0,0))

    def draw_bubble(self, text, pos):
        pad = 8
        r = font_small.render(text, True, (20,20,24))
        w, h = r.get_width()+pad*2, r.get_height()+pad*2
        bubble = pygame.Surface((w, h+10), pygame.SRCALPHA)
        pygame.draw.rect(bubble, (255,255,255,235), (0,0,w,h), border_radius=10)
        pygame.draw.polygon(bubble, (255,255,255,235), [(w//2-7,h),(w//2+7,h),(w//2,h+10)])
        pygame.draw.rect(bubble, (0,0,0,35), (0,0,w,h), width=2, border_radius=10)
        bubble.blit(r, (pad, pad))
        x = pos[0] - w//2; y = pos[1] - h - 18
        screen.blit(bubble, (x,y))

    def draw_hud(self, surf):
        # верхняя панель
        pygame.draw.rect(surf, (0,0,0,120), (0,0,WIDTH,60))
        s1 = text_with_outline(f"Комната: {self.current_room}", font_big, (240,245,255), (0,0,0))
        surf.blit(s1, (16, 12))
        s2 = text_with_outline(f"Счёт: {self.score}", font_big, (240,245,255), (0,0,0))
        surf.blit(s2, (WIDTH - s2.get_width() - 16, 12))

        # нижний HUD
        draw_rage_bar(surf, self.player)
        draw_xp_bar(surf, self.player)
        draw_minimap(surf, self.current_room, self.piz_room)

        if self.toast_t > 0 and self.toast:
            rect = pygame.Rect(WIDTH//2-300, HEIGHT-90, 600, 46)
            hud_panel(surf, rect)
            surf.blit(font_mid.render(self.toast, True, (240,240,255)), (rect.x+16, rect.y+10))

# ====== MAIN ======
def main():
    show_intro()
    menu = MainMenu()
    while True:
        events = pygame.event.get()
        res = menu.update(events)
        menu.draw(screen)
        pygame.display.flip()
        clock.tick(FPS)
        if res == "Играть":
            break
        if res == "Выход":
            pygame.quit(); sys.exit(0)

    # фон: делюкс-градиентный с легкой виньеткой
    global flash_overlay, particles
    flash_overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA); flash_overlay.fill((255,180,100,180)); flash_overlay.set_alpha(0)
    particles = ParticleSystem()

    game = Game()
    last = time.perf_counter()
    while True:
        now = time.perf_counter(); dt = min(0.03, now-last); last = now
        keys = pygame.key.get_pressed()
        game.update(dt, keys)
        game.render(screen)
        pygame.display.flip()
        clock.tick(FPS)

if __name__ == "__main__":
    main()
