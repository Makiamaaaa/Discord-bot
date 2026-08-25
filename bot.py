import os
import random
import re
from datetime import datetime
from threading import Thread

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands, tasks
from flask import Flask

# --- SERVIDOR WEB FLASK (Mantener activo a Lumen en Render) ---
app = Flask("")


@app.route("/")
def home():
  return "🦊 Lumen está despierto y vigilando Elaris 24/7."


def run_flask():
  app.run(host="0.0.0.0", port=8080)


def keep_alive():
  t = Thread(target=run_flask)
  t.start()


# --- BASE DE DATOS Y CONFIGURACIÓN ---
DB_NAME = "elaris_lumen.db"

# --- D&D 2024: RAZAS Y CLASES OFICIALES ---
VALID_RACES = [
    "Humano",
    "Elfo",
    "Enano",
    "Halfling",
    "Orco",
    "Tiefling",
    "Dragonborn",
    "Gnomo",
    "Goliath",
    "Aasimar",
]

CLASS_GROWTH = {
    "BARBARO": {"hp": 30, "fuerza": 4, "defensa": 2, "agilidad": 1, "magia": 0},
    "BARDO": {"hp": 15, "fuerza": 0, "defensa": 1, "agilidad": 2, "magia": 4},
    "BRUJO": {"hp": 15, "fuerza": 0, "defensa": 1, "agilidad": 1, "magia": 4},
    "CLÉRIGO": {"hp": 20, "fuerza": 2, "defensa": 3, "agilidad": 0, "magia": 3},
    "DRUIDA": {"hp": 18, "fuerza": 1, "defensa": 2, "agilidad": 1, "magia": 4},
    "EXPLORADOR": {"hp": 20, "fuerza": 2, "defensa": 1, "agilidad": 3, "magia": 1},
    "GUERRERO": {"hp": 25, "fuerza": 3, "defensa": 3, "agilidad": 1, "magia": 0},
    "HECHICERO": {"hp": 12, "fuerza": 0, "defensa": 1, "agilidad": 1, "magia": 5},
    "MAGO": {"hp": 10, "fuerza": 0, "defensa": 1, "agilidad": 1, "magia": 5},
    "MONJE": {"hp": 18, "fuerza": 2, "defensa": 1, "agilidad": 4, "magia": 0},
    "PALADÍN": {"hp": 25, "fuerza": 3, "defensa": 3, "agilidad": 0, "magia": 2},
    "PÍCARO": {"hp": 15, "fuerza": 1, "defensa": 1, "agilidad": 4, "magia": 0},
}

# --- SISTEMA DE DIFICULTADES Y MAZMORRAS AJUSTADO ---
DUNGEON_TIERS = {
    "Fácil": {
        "weight": 50,
        "dc": 10,
        "loot": "Mineral de Hierro",
        "qty": (1, 3),
        "soles": 50,
    },
    "Normal": {
        "weight": 30,
        "dc": 14,
        "loot": "Hongo Abisal",
        "qty": (2, 4),
        "soles": 150,
    },
    "Difícil": {
        "weight": 13,
        "dc": 18,
        "loot": "Madera Antigua",
        "qty": (3, 5),
        "soles": 400,
    },
    "Épica": {
        "weight": 6,
        "dc": 22,
        "loot": "Fragmento de Alma",
        "qty": (4, 6),
        "soles": 1000,
    },
    "Legendaria": {
        "weight": 1,
        "dc": 26,
        "loot": "Hierba Curativa",
        "qty": (5, 8),
        "soles": 2500,
    },
}

CRAFTING_RECIPES = {
    "Poción de Vida": {"Mineral de Hierro": 1, "Hongo Abisal": 2},
    "Elixir Astral": {"Fragmento de Alma": 2, "Hierba Curativa": 2},
}

DIFFICULTIES = {
    "Fácil": {"exp": 100, "soles": 100, "copas": 1, "favor": 0},
    "Normal": {"exp": 250, "soles": 250, "copas": 2, "favor": 1},
    "Difícil": {"exp": 500, "soles": 500, "copas": 4, "favor": 2},
    "Épica": {"exp": 900, "soles": 900, "copas": 7, "favor": 4},
    "Legendaria": {"exp": 1500, "soles": 1500, "copas": 12, "favor": 7},
}

SLOT_PRICE_COPPER = 10000
CLAN_COST_COPPER = 5000


def format_currency(total_copper: int, icons: dict) -> str:
  plat = total_copper // 1000
  rem = total_copper % 1000
  oro = rem // 100
  rem = rem % 100
  plata = rem // 10
  cobre = rem % 10

  parts = []
  if plat > 0:
    parts.append(f"{plat} {icons.get('platino', '🪙')}")
  if oro > 0:
    parts.append(f"{oro} {icons.get('oro', '🥇')}")
  if plata > 0:
    parts.append(f"{plata} {icons.get('plata', '🥈')}")
  if cobre > 0 or not parts:
    parts.append(f"{cobre} {icons.get('cobre', '🥉')}")

  return " | ".join(parts)


async def get_server_icons(db) -> dict:
  async with db.execute("SELECT key, emoji FROM custom_icons") as cursor:
    rows = await cursor.fetchall()
  defaults = {
      "platino": "🪙",
      "oro": "🥇",
      "plata": "🥈",
      "cobre": "🥉",
      "copas": "🏆",
      "favor": "🙏",
  }
  for key, emoji in rows:
    defaults[key] = emoji
  return defaults


async def init_db():
  async with aiosqlite.connect(DB_NAME) as db:
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS characters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            age INTEGER,
            race TEXT,
            character_class TEXT,
            clan TEXT DEFAULT 'Sin clan',
            level INTEGER DEFAULT 1,
            exp INTEGER DEFAULT 0,
            hp INTEGER DEFAULT 100,
            fuerza INTEGER DEFAULT 10,
            defensa INTEGER DEFAULT 10,
            agilidad INTEGER DEFAULT 10,
            magia INTEGER DEFAULT 10,
            soles INTEGER DEFAULT 100,
            copas INTEGER DEFAULT 0,
            favor_divino INTEGER DEFAULT 0,
            daily_explores INTEGER DEFAULT 2,
            last_daily TEXT DEFAULT '',
            is_active INTEGER DEFAULT 0,
            image_url TEXT DEFAULT '',
            status TEXT DEFAULT 'pendiente',
            review_comment TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS pvp_consent (
            user_a INTEGER NOT NULL,
            user_b INTEGER NOT NULL,
            PRIMARY KEY (user_a, user_b)
        );

        CREATE TABLE IF NOT EXISTS character_slots (
            user_id INTEGER PRIMARY KEY,
            extra_slots INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            char_id INTEGER,
            item_name TEXT NOT NULL,
            quantity INTEGER DEFAULT 1,
            UNIQUE(char_id, item_name),
            FOREIGN KEY (char_id) REFERENCES characters (id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS shops (
            owner_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT
        );

        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_id INTEGER,
            name TEXT NOT NULL,
            description TEXT,
            price INTEGER NOT NULL,
            image_url TEXT,
            stock INTEGER DEFAULT -1,
            FOREIGN KEY (shop_id) REFERENCES shops (owner_id)
        );

        CREATE TABLE IF NOT EXISTS custom_icons (
            key TEXT PRIMARY KEY,
            emoji TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS command_permissions (
            command_name TEXT PRIMARY KEY,
            role_id INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS weather_config (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            channel_id INTEGER
        );

        CREATE TABLE IF NOT EXISTS abyss_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            state_name TEXT,
            modifier INTEGER,
            weather TEXT
        );
        """)

    await db.execute("""
            INSERT OR IGNORE INTO abyss_state (id, state_name, modifier, weather)
            VALUES (1, 'Estable', 0, 'Soplado por una brisa serena sobre Elaris')
        """)
    await db.commit()


def get_required_exp(level: int) -> int:
  return level * 100


async def get_active_character(db, user_id: int):
  async with db.execute(
      "SELECT * FROM characters WHERE user_id = ? AND is_active = 1 AND status"
      " = 'aprobado'",
      (user_id,),
  ) as cursor:
    return await cursor.fetchone()


async def check_command_perm(
    interaction: discord.Interaction, command_name: str
) -> bool:
  if interaction.user.guild_permissions.administrator:
    return True
  async with aiosqlite.connect(DB_NAME) as db:
    async with db.execute(
        "SELECT role_id FROM command_permissions WHERE command_name = ?",
        (command_name,),
    ) as cursor:
      row = await cursor.fetchone()
      if not row:
        return True
      required_role = row[0]
      user_role_ids = [r.id for r in interaction.user.roles]
      return required_role in user_role_ids


async def has_bilateral_pvp(db, user1_id: int, user2_id: int) -> bool:
  async with db.execute(
      "SELECT COUNT(*) FROM pvp_consent WHERE (user_a = ? AND user_b = ?) OR"
      " (user_a = ? AND user_b = ?)",
      (user1_id, user2_id, user2_id, user1_id),
  ) as cursor:
    count = (await cursor.fetchone())[0]
    return count >= 2


async def add_exp_to_character(
    db, char_id: int, exp_amount: int
) -> tuple[bool, int]:
  async with db.execute(
      "SELECT level, exp, character_class, hp, fuerza, defensa, agilidad, magia"
      " FROM characters WHERE id = ?",
      (char_id,),
  ) as cursor:
    row = await cursor.fetchone()
    if not row:
      return False, 0

  level, current_exp, c_class, hp, str_, def_, agi, mag = row
  current_exp += exp_amount
  leveled_up = False

  req_exp = get_required_exp(level)
  while current_exp >= req_exp:
    current_exp -= req_exp
    level += 1
    req_exp = get_required_exp(level)
    leveled_up = True

    growth = CLASS_GROWTH.get(
        c_class.upper(),
        {"hp": 10, "fuerza": 1, "defensa": 1, "agilidad": 1, "magia": 1},
    )
    hp += growth["hp"]
    str_ += growth["fuerza"]
    def_ += growth["defensa"]
    agi += growth["agilidad"]
    mag += growth["magia"]

  await db.execute(
      """
        UPDATE characters 
        SET level = ?, exp = ?, hp = ?, fuerza = ?, defensa = ?, agilidad = ?, magia = ?
        WHERE id = ?
    """,
      (level, current_exp, hp, str_, def_, agi, mag, char_id),
  )
  await db.commit()
  return leveled_up, level


class RulesAcceptView(discord.ui.View):

  def __init__(self, char_modal_data):
    super().__init__(timeout=120)
    self.data = char_modal_data

  @discord.ui.button(
      label="Acepto las reglas de creación", style=discord.ButtonStyle.green
  )
  async def accept(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    async with aiosqlite.connect(DB_NAME) as db:
      await db.execute(
          """
                INSERT INTO characters (
                    user_id, name, age, race, character_class, clan, 
                    fuerza, defensa, agilidad, magia, is_active, image_url, status
                )
                VALUES (?, ?, ?, ?, ?, 'Sin clan', 10, 10, 10, 10, 0, ?, 'pendiente')
            """,
          (
              interaction.user.id,
              self.data["name"],
              self.data["age"],
              self.data["race"],
              self.data["c_class"],
              self.data["image"],
          ),
      )
      await db.commit()

    await interaction.response.edit_message(
        content=(
            f"📜 Ficha de **{self.data['name']}** enviada correctamente."
            " Queda en estado **pendiente** a la espera de revisión por un"
            " moderador."
        ),
        view=None,
    )


class CharacterModal(discord.ui.Modal, title="Crear Personaje D&D 2024"):
  name_input = discord.ui.TextInput(
      label="Nombre", placeholder="Ej: Varis Vaelen", required=True
  )
  age_input = discord.ui.TextInput(
      label="Edad", placeholder="Ej: 28", required=True
  )
  race_input = discord.ui.TextInput(
      label="Raza D&D 2024",
      placeholder="Humano, Elfo, Enano, Halfling, Orco, Tiefling...",
      required=True,
  )
  class_input = discord.ui.TextInput(
      label="Clase D&D 2024",
      placeholder="Guerrero, Mago, Pícaro, Bárbaro, Bardo, Clérigo...",
      required=True,
  )
  image_input = discord.ui.TextInput(
      label="URL de la Imagen (Opcional)",
      placeholder="https://i.imgur.com/...",
      required=False,
  )

  async def on_submit(self, interaction: discord.Interaction):
    try:
      age = int(self.age_input.value)
    except ValueError:
      return await interaction.response.send_message(
          "🦊 La edad debe ser un número entero.", ephemeral=True
      )

    race_matched = next(
        (r for r in VALID_RACES if r.lower() == self.race_input.value.strip().lower()),
        None,
    )
    if not race_matched:
      races_str = ", ".join(VALID_RACES)
      return await interaction.response.send_message(
          f"🦊 Raza no válida según D&D 2024. Elige entre:\n`{races_str}`",
          ephemeral=True,
      )

    c_class_formatted = self.class_input.value.strip().upper()
    if c_class_formatted not in CLASS_GROWTH:
      classes_str = ", ".join(CLASS_GROWTH.keys())
      return await interaction.response.send_message(
          f"🦊 Clase no válida según D&D 2024. Elige entre:\n`{classes_str}`",
          ephemeral=True,
      )

    char_data = {
        "name": self.name_input.value,
        "age": age,
        "race": race_matched,
        "c_class": c_class_formatted,
        "image": self.image_input.value,
    }

    embed = discord.Embed(
        title="⚠️ Normas de Creación de Personaje",
        description=(
            "1. **No memes o personajes de chiste.**\n"
            "2. **Regla del 10 activa:** Ninguna estadística base puede ser inferior a 10.\n"
            "3. **No copias exactas** de obras existentes.\n"
            "4. La ficha pasará por revisión antes de poder ser activada."
        ),
        color=discord.Color.gold(),
    )
    view = RulesAcceptView(char_data)
    await interaction.response.send_message(
        embed=embed, view=view, ephemeral=True
    )


class EventJoinView(discord.ui.View):

  def __init__(self, master_name: str, max_participants: int):
    super().__init__(timeout=None)
    self.master_name = master_name
    self.max_participants = max_participants
    self.participants = []

  @discord.ui.button(
      label="Alistarse (0)",
      style=discord.ButtonStyle.green,
      custom_id="event_join_btn",
      emoji="⚔️",
  )
  async def join_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    user_mention = interaction.user.mention
    if user_mention in self.participants:
      self.participants.remove(user_mention)
      msg = "🦊 Te has retirado del evento."
    else:
      if len(self.participants) >= self.max_participants:
        return await interaction.response.send_message(
            "🦊 El evento ya alcanzó el cupo máximo de participantes.",
            ephemeral=True,
        )
      self.participants.append(user_mention)
      msg = "⚔️ ¡Te has inscrito en la misión!"

    button.label = f"Alistarse ({len(self.participants)}/{self.max_participants})"
    embed = interaction.message.embeds[0]
    part_list = (
        "\n".join(self.participants) if self.participants else "Nadie aún."
    )
    embed.set_field_at(
        0,
        name=f"👥 Participantes ({len(self.participants)}/{self.max_participants})",
        value=part_list,
        inline=False,
    )
    await interaction.message.edit(embed=embed, view=self)
    await interaction.response.send_message(msg, ephemeral=True)


class SwitchCharacterSelect(discord.ui.Select):

  def __init__(self, characters):
    options = [
        discord.SelectOption(
            label=f"{char[2]} (Nvl. {char[7]} {char[5]})",
            value=str(char[0]),
            description="Seleccionar como personaje activo",
        )
        for char in characters
    ]
    super().__init__(
        placeholder="Selecciona tu personaje activo...", options=options
    )

  async def callback(self, interaction: discord.Interaction):
    selected_id = int(self.values[0])
    async with aiosqlite.connect(DB_NAME) as db:
      async with db.execute(
          "SELECT status FROM characters WHERE id = ?", (selected_id,)
      ) as cursor:
        row = await cursor.fetchone()
        if not row or row[0] != "aprobado":
          return await interaction.response.send_message(
              "🦊 Solo puedes activar fichas que hayan sido aprobadas por"
              " moderación.",
              ephemeral=True,
          )

      await db.execute(
          "UPDATE characters SET is_active = 0 WHERE user_id = ?",
          (interaction.user.id,),
      )
      await db.execute(
          "UPDATE characters SET is_active = 1 WHERE id = ?", (selected_id,)
      )
      await db.commit()

    await interaction.response.send_message(
        "🦊 Has cambiado de personaje activo correctamente.", ephemeral=True
    )


class SwitchCharacterView(discord.ui.View):

  def __init__(self, characters):
    super().__init__(timeout=60)
    self.add_item(SwitchCharacterSelect(characters))


class ProductModal(discord.ui.Modal, title="Crear Producto"):
  p_name = discord.ui.TextInput(label="Nombre del Producto", required=True)
  p_desc = discord.ui.TextInput(
      label="Descripción", style=discord.TextStyle.paragraph, required=True
  )
  p_price = discord.ui.TextInput(label="Precio (Coronas Cobre)", required=True)
  p_img = discord.ui.TextInput(label="URL de Imagen", required=False)
  p_stock = discord.ui.TextInput(
      label="Stock (-1 para infinito)", default="-1", required=True
  )

  async def on_submit(self, interaction: discord.Interaction):
    try:
      price = int(self.p_price.value)
      stock = int(self.p_stock.value)
    except ValueError:
      return await interaction.response.send_message(
          "🦊 El precio y el stock deben ser números.", ephemeral=True
      )

    async with aiosqlite.connect(DB_NAME) as db:
      await db.execute(
          """
                INSERT INTO products (shop_id, name, description, price, image_url, stock)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
          (
              interaction.user.id,
              self.p_name.value,
              self.p_desc.value,
              price,
              self.p_img.value,
              stock,
          ),
      )
      await db.commit()

    await interaction.response.send_message(
        f"🏪 Producto **{self.p_name.value}** añadido a tu tienda."
    )


class CatalogPaginator(discord.ui.View):

  def __init__(self, products, shop_name, icons):
    super().__init__(timeout=120)
    self.products = products
    self.shop_name = shop_name
    self.icons = icons
    self.index = 0

  def build_embed(self) -> discord.Embed:
    item = self.products[self.index]
    price_formatted = format_currency(item[3], self.icons)
    embed = discord.Embed(
        title=f"🏪 {self.shop_name}",
        description=f"**{item[1]}**\n\n{item[2]}",
        color=discord.Color.gold(),
    )
    embed.add_field(name="Precio", value=price_formatted, inline=True)
    stock_str = "Infinito" if item[5] == -1 else str(item[5])
    embed.add_field(name="Stock", value=stock_str, inline=True)
    if item[4]:
      embed.set_image(url=item[4])
    embed.set_footer(
        text=f"Producto {self.index + 1}/{len(self.products)} | ID: {item[0]}"
    )
    return embed

  @discord.ui.button(label="◀ Anterior", style=discord.ButtonStyle.blurple)
  async def prev_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    if self.index > 0:
      self.index -= 1
      await interaction.response.edit_message(
          embed=self.build_embed(), view=self
      )
    else:
      await interaction.response.defer()

  @discord.ui.button(label="Siguiente ▶", style=discord.ButtonStyle.blurple)
  async def next_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    if self.index < len(self.products) - 1:
      self.index += 1
      await interaction.response.edit_message(
          embed=self.build_embed(), view=self
      )
    else:
      await interaction.response.defer()


class MissionRewardView(discord.ui.View):

  def __init__(self, master_user):
    super().__init__(timeout=180)
    self.master_user = master_user
    self.selected_difficulty = "Fácil"
    self.selected_users = []

  @discord.ui.select(
      placeholder="Selecciona la dificultad...",
      options=[discord.SelectOption(label=k) for k in DIFFICULTIES.keys()],
  )
  async def select_difficulty(
      self, interaction: discord.Interaction, select: discord.ui.Select
  ):
    self.selected_difficulty = select.values[0]
    await interaction.response.defer()

  @discord.ui.select(
      cls=discord.ui.UserSelect,
      placeholder="Selecciona los participantes...",
      min_values=1,
      max_values=10,
  )
  async def select_users(
      self, interaction: discord.Interaction, select: discord.ui.UserSelect
  ):
    self.selected_users = select.values
    await interaction.response.defer()

  @discord.ui.button(
      label="Entregar recompensas", style=discord.ButtonStyle.green
  )
  async def confirm(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    if interaction.user != self.master_user:
      return await interaction.response.send_message(
          "🦊 No eres el Master de esta sesión.", ephemeral=True
      )
    if not self.selected_users:
      return await interaction.response.send_message(
          "🦊 Selecciona al menos a un participante.", ephemeral=True
      )

    rewards = DIFFICULTIES[self.selected_difficulty]
    lvl_msgs = []

    async with aiosqlite.connect(DB_NAME) as db:
      icons = await get_server_icons(db)
      money_str = format_currency(rewards["soles"], icons)

      for user in self.selected_users:
        active_char = await get_active_character(db, user.id)
        if active_char:
          char_id = active_char[0]
          await db.execute(
              """
                        UPDATE characters 
                        SET soles = soles + ?, copas = copas + ?, favor_divino = favor_divino + ?
                        WHERE id = ?
                    """,
              (rewards["soles"], rewards["copas"], rewards["favor"], char_id),
          )
          leveled_up, new_lvl = await add_exp_to_character(
              db, char_id, rewards["exp"]
          )
          if leveled_up:
            lvl_msgs.append(
                f"✨ **{active_char[2]}** ({user.display_name}) subió al **Nivel"
                f" {new_lvl}**!"
            )
      await db.commit()

    embed = discord.Embed(
        title="🌙 Recompensas Entregadas",
        description=(
            f"**Dificultad:** {self.selected_difficulty}\n**Participantes:**"
            f" {', '.join([u.mention for u in self.selected_users])}\n\n**Recompensa"
            f" individual:**\n💰 {money_str} | {icons['copas']} {rewards['copas']}"
            f" Copas | {icons['favor']} {rewards['favor']} Favor Divino\n✨"
            f" {rewards['exp']} EXP"
        ),
        color=discord.Color.purple(),
    )
    if lvl_msgs:
      embed.add_field(
          name="🦊 Subidas de Nivel", value="\n".join(lvl_msgs), inline=False
      )
    await interaction.response.send_message(embed=embed)
    self.stop()


# --- INTERFAZ DE NAVEGACIÓN EN MAZMORRAS AJUSTADA ---
class DungeonExploreView(discord.ui.View):

  def __init__(self, char_id, stats, abyss_mod, tier_name, tier_info):
    super().__init__(timeout=60)
    self.char_id = char_id
    self.stats = stats
    self.abyss_mod = abyss_mod
    self.tier_name = tier_name
    self.tier_info = tier_info

  @discord.ui.button(
      label="🗝️ Entrar a la Cueva", style=discord.ButtonStyle.green
  )
  async def enter_dungeon(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    for child in self.children:
      child.disabled = True

    roll = random.randint(1, 20)
    best_mod = (
        max(self.stats["fuerza"], self.stats["agilidad"]) - 10
    ) // 2  # Modificador D&D
    total = roll + best_mod + self.abyss_mod
    required_dc = self.tier_info["dc"]

    if total >= required_dc:
      qty = random.randint(*self.tier_info["qty"])
      soles_earned = self.tier_info["soles"]
      loot_item = self.tier_info["loot"]

      async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            """
                    INSERT INTO inventory (char_id, item_name, quantity)
                    VALUES (?, ?, ?)
                    ON CONFLICT(char_id, item_name) DO UPDATE SET quantity = quantity + ?
                """,
            (self.char_id, loot_item, qty, qty),
        )
        await db.execute(
            "UPDATE characters SET soles = soles + ? WHERE id = ?",
            (soles_earned, self.char_id),
        )
        icons = await get_server_icons(db)
        await db.commit()

      soles_str = format_currency(soles_earned, icons)
      embed = discord.Embed(
          title=f"🦊 Mazmorra {self.tier_name}: ¡CONQUISTADA!",
          description=(
              f"Superaste los peligros de la cueva (Dificultad {required_dc}).\n\n"
              f"🎲 **Tirada:** {roll} | **Mod. Atributo:** {best_mod:+d} | **Mod. Abismo:** {self.abyss_mod:+d} = **Total: {total}**\n\n"
              f"🎒 **Botín Obtenido:** `{loot_item} x{qty}`\n"
              f"💰 **Recompensa:** {soles_str}"
          ),
          color=discord.Color.green(),
      )
    else:
      embed = discord.Embed(
          title=f"🦊 Mazmorra {self.tier_name}: FALLIDA",
          description=(
              f"La dificultad superó a tu personaje (Requerido: {required_dc}).\n\n"
              f"🎲 **Tirada:** {roll} | **Total:** **{total}**\n"
              "*Tuviste que escapar con las manos vacías antes de ser atrapado.*"
          ),
          color=discord.Color.red(),
      )
    await interaction.response.edit_message(embed=embed, view=self)


# --- CONFIGURACIÓN DEL BOT ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
  await init_db()
  await bot.tree.sync()
  daily_weather_task.start()
  print(f"🦊 Lumen se ha despertado como {bot.user}")


@tasks.loop(hours=24)
async def daily_weather_task():
  await bot.wait_until_ready()
  async with aiosqlite.connect(DB_NAME) as db:
    async with db.execute(
        "SELECT channel_id FROM weather_config WHERE id = 1"
    ) as cursor:
      row = await cursor.fetchone()
      if not row or not row[0]:
        return
      channel_id = row[0]

    states = [
        ("Sereno", 0, "Una brisa pacífica recorre Elaris."),
        ("Niebla Abisal", -1, "Miasma denso reduce la visibilidad."),
        ("Tormenta de Almas", 2, "La energía del Abismo fortalece los dados."),
    ]
    st_name, st_mod, st_weather = random.choice(states)
    await db.execute(
        """
            UPDATE abyss_state SET state_name = ?, modifier = ?, weather = ? WHERE id = 1
        """,
        (st_name, st_mod, st_weather),
    )
    await db.commit()

  channel = bot.get_channel(channel_id)
  if channel:
    embed = discord.Embed(
        title="🌌 Reporte Diario del Clima y del Abismo",
        description=(
            f"**Estado del Abismo:** {st_name} (Modificador:"
            f" {st_mod})\n**Clima:** {st_weather}"
        ),
        color=discord.Color.dark_purple(),
    )
    embed.set_footer(text="🦊 Lumen vigila los cambios de Elaris.")
    await channel.send(embed=embed)


# --- COMANDOS PRINCIPALES Y DE NAVEGACIÓN ---
@bot.tree.command(name="lumen", description="Muestra la información de Lumen")
async def lumen_info(interaction: discord.Interaction):
  embed = discord.Embed(
      title="🦊🐾 Lumen, el Zorro Guía de Elaris",
      description=(
          "🦊 Una nueva alma ha llegado. Procura no perderte antes de encontrar"
          " tu nombre.\n\nCamino entre los senderos y sombras de Elaris para"
          " asegurarme de que no caigas al Abismo... o al menos para verlo si"
          " ocurre."
      ),
      color=discord.Color.orange(),
  )
  embed.set_footer(
      text="✦ Elaris Roleplay | Usa /ayuda para ver tus opciones."
  )
  await interaction.response.send_message(embed=embed)


@bot.tree.command(name="ayuda", description="Lista de comandos disponibles")
async def ayuda(interaction: discord.Interaction):
  embed = discord.Embed(
      title="🦊 Guía de Caminantes de Elaris",
      description="Lumen te muestra las herramientas disponibles para tu travesía:",
      color=discord.Color.gold(),
  )
  embed.add_field(
      name="📜 Personajes",
      value=(
          "`/crear-personaje` | `/personaje-estado` | `/mis-personajes` |"
          " `/perfil` | `/crear-clan` | `/comprar-slot`"
      ),
      inline=False,
  )
  embed.add_field(
      name="⚔️ PvP & Seguridad",
      value="`/pvp-consentir` | `/pvp-retirar` | `/mision-crear`",
      inline=False,
  )
  embed.add_field(
      name="🪙 Economía y Mochila",
      value=(
          "`/cuenta` | `/daily` | `/pagar` | `/inventario` | `/usar` |"
          " `/craftear`"
      ),
      inline=False,
  )
  embed.add_field(
      name="🎲 Dados y Aventura",
      value="`/tirar` | `/prueba` | `/explorar` | `/clima`",
      inline=False,
  )
  embed.add_field(
      name="🏪 Mercado",
      value="`/catalogo` | `/tienda crear` | `/tienda producto-crear`",
      inline=False,
  )

  if interaction.user.guild_permissions.administrator:
    embed.add_field(
        name="🔮 Moderación & Master",
        value=(
            "`/personaje-revisar` | `/mision-recompensa` | `/dar-item` |"
            " `/evento-crear` | `/config-iconos` | `/config-clima-canal` |"
            " `/config-permisos`"
        ),
        inline=False,
    )

  embed.set_footer(text="🦊 Si te pierdes, recuerda que los dados no mienten.")
  await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="crear-personaje", description="Crea un nuevo personaje")
async def crear_personaje(interaction: discord.Interaction):
  if not await check_command_perm(interaction, "crear-personaje"):
    return await interaction.response.send_message(
        "🦊 No posees el rol requerido para usar este comando.", ephemeral=True
    )

  async with aiosqlite.connect(DB_NAME) as db:
    async with db.execute(
        "SELECT COUNT(*) FROM characters WHERE user_id = ?",
        (interaction.user.id,),
    ) as cursor:
      count = (await cursor.fetchone())[0]

    async with db.execute(
        "SELECT extra_slots FROM character_slots WHERE user_id = ?",
        (interaction.user.id,),
    ) as cursor:
      slot_row = await cursor.fetchone()
      extra_slots = slot_row[0] if slot_row else 0

    max_allowed = 3 + extra_slots
    if count >= max_allowed:
      return await interaction.response.send_message(
          f"🦊 Has alcanzado el límite de personajes permitido ({count}/{max_allowed})."
          " Compra slots adicionales con `/comprar-slot`.",
          ephemeral=True,
      )

  await interaction.response.send_modal(CharacterModal())


@bot.tree.command(
    name="personaje-estado",
    description="Consulta el estado de tus fichas registradas",
)
async def personaje_estado(interaction: discord.Interaction):
  async with aiosqlite.connect(DB_NAME) as db:
    async with db.execute(
        "SELECT id, name, status, review_comment, is_active FROM characters"
        " WHERE user_id = ?",
        (interaction.user.id,),
    ) as cursor:
      rows = await cursor.fetchall()

  if not rows:
    return await interaction.response.send_message(
        "🦊 No tienes personajes registrados.", ephemeral=True
    )

  embed = discord.Embed(
      title="📜 Estado de tus Personajes", color=discord.Color.blue()
  )
  for char_id, name, status, comment, is_active in rows:
    active_tag = " 🌟 [ACTIVO]" if is_active == 1 else ""
    st_emoji = "✅" if status == "aprobado" else "⏳" if status == "pendiente" else "❌"
    val = f"**Estado:** {st_emoji} {status.capitalize()}"
    if comment:
      val += f"\n**Comentario:** {comment}"
    embed.add_field(name=f"{name} (ID: {char_id}){active_tag}", value=val, inline=False)

  await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(
    name="personaje-revisar",
    description="Aprueba o rechaza la ficha de un usuario",
)
@app_commands.checks.has_permissions(administrator=True)
async def personaje_revisar(
    interaction: discord.Interaction,
    id_personaje: int,
    accion: str,
    comentario: str = "",
):
  acc = accion.lower().strip()
  if acc not in ["aprobar", "rechazar"]:
    return await interaction.response.send_message(
        "🦊 Acción inválida. Usa `aprobar` o `rechazar`.", ephemeral=True
    )

  async with aiosqlite.connect(DB_NAME) as db:
    async with db.execute(
        "SELECT user_id, name FROM characters WHERE id = ?", (id_personaje,)
    ) as cursor:
      row = await cursor.fetchone()
      if not row:
        return await interaction.response.send_message(
            "🦊 No se encontró esa ficha.", ephemeral=True
        )
      target_user_id, char_name = row

    new_status = "aprobado" if acc == "aprobar" else "rechazado"

    if new_status == "aprobado":
      await db.execute(
          "UPDATE characters SET is_active = 0 WHERE user_id = ?",
          (target_user_id,),
      )
      await db.execute(
          "UPDATE characters SET status = 'aprobado', review_comment = ?,"
          " is_active = 1 WHERE id = ?",
          (comentario, id_personaje),
      )
    else:
      await db.execute(
          "UPDATE characters SET status = 'rechazado', review_comment = ?,"
          " is_active = 0 WHERE id = ?",
          (comentario, id_personaje),
      )

    await db.commit()

  await interaction.response.send_message(
      f"📜 Ficha **{char_name}** (ID: {id_personaje}) ha sido **{new_status}**."
  )


@bot.tree.command(name="perfil", description="Muestra el perfil del personaje")
async def perfil(interaction: discord.Interaction, usuario: discord.User = None):
  target = usuario or interaction.user
  async with aiosqlite.connect(DB_NAME) as db:
    row = await get_active_character(db, target.id)
    icons = await get_server_icons(db)

  if not row:
    return await interaction.response.send_message(
        "🦊 Esa alma no posee un personaje activo y aprobado en Elaris.",
        ephemeral=True,
    )

  name, age, race, c_class, clan = row[2], row[3], row[4], row[5], row[6]
  level, exp = row[7], row[8]
  hp, str_, def_, agi, mag = row[9], row[10], row[11], row[12], row[13]
  soles_copper, copas, favor = row[14], row[15], row[16]
  img_url = row[21] if len(row) > 21 else ""

  money_str = format_currency(soles_copper, icons)
  req_exp = get_required_exp(level)

  embed = discord.Embed(
      title=f"📜 Ficha de {name}", color=discord.Color.dark_gold()
  )
  if img_url and img_url.startswith("http"):
    embed.set_thumbnail(url=img_url)

  embed.add_field(
      name="General",
      value=(
          f"**Raza:** {race}\n**Edad:** {age}\n**Clase:** {c_class}\n**Clan:**"
          f" {clan}"
      ),
      inline=True,
  )
  embed.add_field(
      name="Progreso",
      value=f"**Nivel:** {level}\n**EXP:** {exp} / {req_exp}",
      inline=True,
  )
  embed.add_field(
      name="Bóveda",
      value=(
          f"💰 {money_str}\n{icons['copas']} **Copas:**"
          f" {copas}\n{icons['favor']} **Favor Divino:** {favor}"
      ),
      inline=False,
  )
  embed.add_field(
      name="Estadísticas",
      value=(
          f"❤️ HP: {hp} | ⚔️ Fuerza: {str_} | 🛡️ Defensa: {def_}\n💨 Agilidad:"
          f" {agi} | ✨ Magia: {mag}"
      ),
      inline=False,
  )

  await interaction.response.send_message(embed=embed)


@bot.tree.command(
    name="mis-personajes",
    description="Lista tus personajes y te permite cambiar el personaje activo",
)
async def mis_personajes(interaction: discord.Interaction):
  async with aiosqlite.connect(DB_NAME) as db:
    async with db.execute(
        "SELECT * FROM characters WHERE user_id = ?", (interaction.user.id,)
    ) as cursor:
      chars = await cursor.fetchall()

  if not chars:
    return await interaction.response.send_message(
        "🦊 Aún no has creado ningún personaje. Usa `/crear-personaje`.",
        ephemeral=True,
    )

  embed = discord.Embed(
      title="📜 Tu Lista de Personajes", color=discord.Color.dark_gold()
  )
  for char in chars:
    active_tag = " 🌟 **[ACTIVO]**" if char[20] == 1 else ""
    st_str = f"({char[22].capitalize()})" if len(char) > 22 else ""
    embed.add_field(
        name=f"{char[2]} (Nvl. {char[7]}) {st_str}{active_tag}",
        value=(
            f"**Clase:** {char[5]} | **Raza:** {char[4]} | **Clan:** {char[6]}"
        ),
        inline=False,
    )

  approved_chars = [c for c in chars if len(c) > 22 and c[22] == "aprobado"]
  view = SwitchCharacterView(approved_chars) if approved_chars else None
  await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


@bot.tree.command(
    name="pvp-consentir", description="Otorga consentimiento de PvP a un usuario"
)
async def pvp_consentir(
    interaction: discord.Interaction, oponente: discord.User
):
  if oponente.id == interaction.user.id:
    return await interaction.response.send_message(
        "🦊 No puedes darte consentimiento PvP a ti mismo.", ephemeral=True
    )

  async with aiosqlite.connect(DB_NAME) as db:
    await db.execute(
        "INSERT OR IGNORE INTO pvp_consent (user_a, user_b) VALUES (?, ?)",
        (interaction.user.id, oponente.id),
    )
    await db.commit()
    is_active = await has_bilateral_pvp(db, interaction.user.id, oponente.id)

  if is_active:
    await interaction.response.send_message(
        f"⚔️ **¡PvP Activado!** Tanto {interaction.user.mention} como"
        f" {oponente.mention} han aceptado el combate libre entre sus"
        " personajes."
    )
  else:
    await interaction.response.send_message(
        f"🛡️ Has registrado tu consentimiento PvP hacia {oponente.mention}."
        " El PvP se activará solo cuando el otro usuario también acepte con"
        " `/pvp-consentir`.",
        ephemeral=True,
    )


@bot.tree.command(
    name="pvp-retirar", description="Revoca el consentimiento de PvP con un usuario"
)
async def pvp_retirar(interaction: discord.Interaction, oponente: discord.User):
  async with aiosqlite.connect(DB_NAME) as db:
    await db.execute(
        "DELETE FROM pvp_consent WHERE (user_a = ? AND user_b = ?) OR (user_a ="
        " ? AND user_b = ?)",
        (interaction.user.id, oponente.id, oponente.id, interaction.user.id),
    )
    await db.commit()

  await interaction.response.send_message(
      f"🛡️ Consentimiento PvP revocado entre {interaction.user.mention} y"
      f" {oponente.mention}. Combatir ahora está restringido."
  )


@bot.tree.command(
    name="mision-crear",
    description="Crea una misión con líneas/semáforos y avisos de contenido",
)
async def mision_crear(
    interaction: discord.Interaction,
    titulo: str,
    descripcion: str,
    aplica_lineas_semaforos: bool,
    advertencias_contenido: str = "Ninguna",
):
  if not await check_command_perm(interaction, "mision-crear"):
    return await interaction.response.send_message(
        "🦊 No tienes permiso para publicar misiones.", ephemeral=True
    )

  if not aplica_lineas_semaforos:
    return await interaction.response.send_message(
        "🦊 Todas las misiones deben aplicar el protocolo de líneas y"
        " semáforos para la seguridad de rol.",
        ephemeral=True,
    )

  embed = discord.Embed(
      title=f"📜 NUEVA MISIÓN: {titulo}",
      description=f"{descripcion}",
      color=discord.Color.dark_purple(),
  )
  embed.add_field(
      name="🛡️ Herramientas de Seguridad",
      value="✅ Líneas y Semáforos obligatorios.",
      inline=False,
  )
  embed.add_field(
      name="⚠️ Avisos de Contenido",
      value=f"`{advertencias_contenido}`",
      inline=False,
  )
  embed.set_footer(text=f"🧙‍♂️ Master: {interaction.user.display_name}")

  await interaction.response.send_message(embed=embed)


@bot.tree.command(
    name="crear-clan",
    description=(
        f"Funda un nuevo clan para tu personaje (Costo: {CLAN_COST_COPPER}"
        " Coronas Cobre)"
    ),
)
async def crear_clan(interaction: discord.Interaction, nombre_clan: str):
  async with aiosqlite.connect(DB_NAME) as db:
    char = await get_active_character(db, interaction.user.id)
    if not char:
      return await interaction.response.send_message(
          "🦊 Necesitas un personaje activo y aprobado.", ephemeral=True
      )

    if char[14] < CLAN_COST_COPPER:
      icons = await get_server_icons(db)
      required_str = format_currency(CLAN_COST_COPPER, icons)
      return await interaction.response.send_message(
          f"🦊 Fundar un clan cuesta **{required_str}**. No tienes suficiente"
          " dinero.",
          ephemeral=True,
      )

    await db.execute(
        "UPDATE characters SET soles = soles - ?, clan = ? WHERE id = ?",
        (CLAN_COST_COPPER, nombre_clan, char[0]),
    )
    await db.commit()

  await interaction.response.send_message(
      f"🛡️ **{char[2]}** ha pagado las tasas y fundado el clan **{nombre_clan}**."
  )


@bot.tree.command(
    name="comprar-slot", description="Compra 1 ranura adicional de personaje"
)
async def comprar_slot(interaction: discord.Interaction):
  user_id = interaction.user.id
  async with aiosqlite.connect(DB_NAME) as db:
    char = await get_active_character(db, user_id)
    if not char:
      return await interaction.response.send_message(
          "🦊 Necesitas al menos un personaje activo y aprobado.",
          ephemeral=True,
      )

    async with db.execute(
        "SELECT extra_slots FROM character_slots WHERE user_id = ?", (user_id,)
    ) as cursor:
      row = await cursor.fetchone()
      extra_slots = row[0] if row else 0

    if extra_slots >= 2:
      return await interaction.response.send_message(
          "🦊 Ya has comprado el número máximo de ranuras adicionales (2"
          " extra).",
          ephemeral=True,
      )

    if char[14] < SLOT_PRICE_COPPER:
      icons = await get_server_icons(db)
      req_str = format_currency(SLOT_PRICE_COPPER, icons)
      return await interaction.response.send_message(
          f"🦊 No tienes suficientes fondos. Necesitas **{req_str}**.",
          ephemeral=True,
      )

    await db.execute(
        "UPDATE characters SET soles = soles - ? WHERE id = ?",
        (SLOT_PRICE_COPPER, char[0]),
    )
    await db.execute(
        """
            INSERT INTO character_slots (user_id, extra_slots) VALUES (?, 1)
            ON CONFLICT(user_id) DO UPDATE SET extra_slots = extra_slots + 1
        """,
        (user_id,),
    )
    await db.commit()

  await interaction.response.send_message(
      "✨ Has comprado 1 ranura de personaje adicional con éxito."
  )


@bot.tree.command(
    name="cuenta", description="Muestra la bóveda de tu personaje activo"
)
async def cuenta(interaction: discord.Interaction):
  async with aiosqlite.connect(DB_NAME) as db:
    char = await get_active_character(db, interaction.user.id)
    icons = await get_server_icons(db)

  if not char:
    return await interaction.response.send_message(
        "🦊 No tienes un personaje activo y aprobado.", ephemeral=True
    )

  money_str = format_currency(char[14], icons)
  embed = discord.Embed(
      title=f"💰 Bóveda Personal de {char[2]}",
      description=(
          f"💰 **Coronas:** {money_str}\n{icons['copas']} **Copas:**"
          f" {char[15]}\n{icons['favor']} **Favor Divino:** {char[16]}"
      ),
      color=discord.Color.gold(),
  )
  await interaction.response.send_message(embed=embed)


@bot.tree.command(
    name="daily", description="Reclama tu recompensa diaria de Coronas"
)
async def daily(interaction: discord.Interaction):
  today = datetime.utcnow().strftime("%Y-%m-%d")
  async with aiosqlite.connect(DB_NAME) as db:
    char = await get_active_character(db, interaction.user.id)
    icons = await get_server_icons(db)

    if not char:
      return await interaction.response.send_message(
          "🦊 No tienes un personaje activo y aprobado.", ephemeral=True
      )

    if char[18] == today:
      return await interaction.response.send_message(
          "🦊 Ya has reclamado tu recompensa del día. Vuelve mañana.",
          ephemeral=True,
      )

    reward_copper = 50
    await db.execute(
        "UPDATE characters SET soles = soles + ?, last_daily = ? WHERE id = ?",
        (reward_copper, today, char[0]),
    )
    await db.commit()

  reward_str = format_currency(reward_copper, icons)
  await interaction.response.send_message(
      f"🦊 Recompensa diaria entregada a **{char[2]}**: **{reward_str}**."
  )


@bot.tree.command(name="pagar", description="Transfiere Coronas a otro jugador")
async def pagar(
    interaction: discord.Interaction, destinatario: discord.User, cantidad_cobre: int
):
  if cantidad_cobre <= 0:
    return await interaction.response.send_message(
        "🦊 La cantidad debe ser mayor a 0.", ephemeral=True
    )
  if destinatario.id == interaction.user.id:
    return await interaction.response.send_message(
        "🦊 No puedes enviarte dinero a ti mismo.", ephemeral=True
    )

  async with aiosqlite.connect(DB_NAME) as db:
    sender = await get_active_character(db, interaction.user.id)
    receiver = await get_active_character(db, destinatario.id)
    icons = await get_server_icons(db)

    if not sender or not receiver:
      return await interaction.response.send_message(
          "🦊 Ambos jugadores deben tener un personaje activo y aprobado.",
          ephemeral=True,
      )

    if sender[14] < cantidad_cobre:
      return await interaction.response.send_message(
          "🦊 No posees suficiente dinero.", ephemeral=True
      )

    await db.execute(
        "UPDATE characters SET soles = soles - ? WHERE id = ?",
        (cantidad_cobre, sender[0]),
    )
    await db.execute(
        "UPDATE characters SET soles = soles + ? WHERE id = ?",
        (cantidad_cobre, receiver[0]),
    )
    await db.commit()

  sent_str = format_currency(cantidad_cobre, icons)
  await interaction.response.send_message(
      f"🪙 **{sender[2]}** ha transferido **{sent_str}** a **{receiver[2]}**"
      f" ({destinatario.mention})."
  )


@bot.tree.command(name="inventario", description="Muestra la mochila del personaje")
async def inventario(interaction: discord.Interaction):
  async with aiosqlite.connect(DB_NAME) as db:
    char = await get_active_character(db, interaction.user.id)
    if not char:
      return await interaction.response.send_message(
          "🦊 No tienes un personaje activo y aprobado.", ephemeral=True
      )

    async with db.execute(
        "SELECT item_name, quantity FROM inventory WHERE char_id = ?", (char[0],)
    ) as cursor:
      rows = await cursor.fetchall()

  if not rows:
    return await interaction.response.send_message(
        f"🦊 La mochila de **{char[2]}** está vacía.", ephemeral=True
    )

  items_str = "\n".join([f"• **{item}**: x{qty}" for item, qty in rows])
  embed = discord.Embed(
      title=f"🎒 Mochila de {char[2]}",
      description=items_str,
      color=discord.Color.dark_green(),
  )
  await interaction.response.send_message(embed=embed)


@bot.tree.command(name="usar", description="Consume un objeto del inventario")
async def usar(interaction: discord.Interaction, item: str):
  async with aiosqlite.connect(DB_NAME) as db:
    char = await get_active_character(db, interaction.user.id)
    if not char:
      return await interaction.response.send_message(
          "🦊 No tienes un personaje activo y aprobado.", ephemeral=True
      )

    async with db.execute(
        "SELECT quantity FROM inventory WHERE char_id = ? AND item_name = ?",
        (char[0], item),
    ) as cursor:
      row = await cursor.fetchone()

    if not row or row[0] <= 0:
      return await interaction.response.send_message(
          "🦊 No posees ese objeto.", ephemeral=True
      )

    if row[0] == 1:
      await db.execute(
          "DELETE FROM inventory WHERE char_id = ? AND item_name = ?",
          (char[0], item),
      )
    else:
      await db.execute(
          "UPDATE inventory SET quantity = quantity - 1 WHERE char_id = ? AND"
          " item_name = ?",
          (char[0], item),
      )
    await db.commit()

  await interaction.response.send_message(
      f"✨ **{char[2]}** ha utilizado **{item}**."
  )


@bot.tree.command(name="craftear", description="Combina materiales")
async def craftear(interaction: discord.Interaction, receta: str):
  if receta not in CRAFTING_RECIPES:
    recetas_list = ", ".join(CRAFTING_RECIPES.keys())
    return await interaction.response.send_message(
        f"🦊 Receta no encontrada. Disponibles: {recetas_list}", ephemeral=True
    )

  ingredients = CRAFTING_RECIPES[receta]
  async with aiosqlite.connect(DB_NAME) as db:
    char = await get_active_character(db, interaction.user.id)
    if not char:
      return await interaction.response.send_message(
          "🦊 No tienes un personaje activo y aprobado.", ephemeral=True
      )

    for ing, req_qty in ingredients.items():
      async with db.execute(
          "SELECT quantity FROM inventory WHERE char_id = ? AND item_name = ?",
          (char[0], ing),
      ) as cursor:
        row = await cursor.fetchone()
        if not row or row[0] < req_qty:
          return await interaction.response.send_message(
              f"🦊 Te faltan materiales: {ing} (necesitas {req_qty}).",
              ephemeral=True,
          )

    for ing, req_qty in ingredients.items():
      await db.execute(
          "UPDATE inventory SET quantity = quantity - ? WHERE char_id = ? AND"
          " item_name = ?",
          (req_qty, char[0], ing),
      )

    await db.execute(
        """
            INSERT INTO inventory (char_id, item_name, quantity)
            VALUES (?, ?, 1)
            ON CONFLICT(char_id, item_name) DO UPDATE SET quantity = quantity + 1
        """,
        (char[0], receta),
    )
    await db.commit()

  await interaction.response.send_message(
      f"🛠️ **{char[2]}** ha fabricado con éxito: **{receta}**."
  )


@bot.tree.command(name="dar-item", description="Otorga un ítem a un jugador")
async def dar_item(
    interaction: discord.Interaction, usuario: discord.User, item: str, cantidad: int
):
  if not await check_command_perm(interaction, "dar-item"):
    return await interaction.response.send_message(
        "🦊 No tienes permisos para este comando.", ephemeral=True
    )

  if cantidad <= 0:
    return await interaction.response.send_message(
        "🦊 La cantidad debe ser mayor a 0.", ephemeral=True
    )

  async with aiosqlite.connect(DB_NAME) as db:
    char = await get_active_character(db, usuario.id)
    if not char:
      return await interaction.response.send_message(
          "🦊 El objetivo no tiene un personaje activo y aprobado.",
          ephemeral=True,
      )

    await db.execute(
        """
            INSERT INTO inventory (char_id, item_name, quantity)
            VALUES (?, ?, ?)
            ON CONFLICT(char_id, item_name) DO UPDATE SET quantity = quantity + ?
        """,
        (char[0], item, cantidad, cantidad),
    )
    await db.commit()

  await interaction.response.send_message(
      f"🎒 Entregado `{item} x{cantidad}` al personaje **{char[2]}** de"
      f" {usuario.mention}."
  )


@bot.tree.command(name="tirar", description="Lanza dados (Ejemplo: 1d20+3, 2d6)")
async def tirar(interaction: discord.Interaction, formula: str):
  match = re.match(r"^(\d+)d(\d+)(?:([+-])(\d+))?$", formula.lower().strip())
  if not match:
    return await interaction.response.send_message(
        "🦊 Formato inválido. Usa la notación: 1d20, 2d6+2, etc.", ephemeral=True
    )

  num_dice = int(match.group(1))
  sides = int(match.group(2))
  sign = match.group(3)
  mod = int(match.group(4)) if match.group(4) else 0

  if num_dice > 20 or sides > 100:
    return await interaction.response.send_message(
        "🦊 Demasiados dados o caras.", ephemeral=True
    )

  rolls = [random.randint(1, sides) for _ in range(num_dice)]
  raw_total = sum(rolls)
  final_total = (
      raw_total + mod
      if sign == "+"
      else raw_total - mod
      if sign == "-"
      else raw_total
  )

  rolls_str = ", ".join(map(str, rolls))
  mod_str = f" {sign} {mod}" if sign else ""

  crit_msg = ""
  if num_dice == 1 and sides == 20:
    if rolls[0] == 20:
      crit_msg = " 🔥 **¡CRÍTICO NATURAL!**"
    elif rolls[0] == 1:
      crit_msg = " 💀 **¡PIFIA NATURAL!**"

  embed = discord.Embed(
      title="🎲 Tirada de Dados",
      description=(
          f"**Fórmula:** `{formula}`\n**Resultados:**"
          f" `[{rolls_str}]`{mod_str}\n**Total:** **{final_total}**{crit_msg}"
      ),
      color=discord.Color.blue(),
  )
  embed.set_footer(text="🦊 El destino acaba de lanzar los dados.")
  await interaction.response.send_message(embed=embed)


@bot.tree.command(name="prueba", description="Prueba de atributo D&D")
async def prueba(interaction: discord.Interaction, atributo: str):
  attr = atributo.lower().strip()
  if attr not in ["fuerza", "defensa", "agilidad", "magia"]:
    return await interaction.response.send_message(
        "🦊 Atributos permitidos: Fuerza, Defensa, Agilidad, Magia.",
        ephemeral=True,
    )

  async with aiosqlite.connect(DB_NAME) as db:
    char = await get_active_character(db, interaction.user.id)
    if not char:
      return await interaction.response.send_message(
          "🦊 No tienes un personaje activo y aprobado.", ephemeral=True
      )

    attr_index = {"fuerza": 10, "defensa": 11, "agilidad": 12, "magia": 13}[attr]
    attr_val = char[attr_index]

  mod_dnd = (attr_val - 10) // 2
  roll = random.randint(1, 20)
  total = roll + mod_dnd

  embed = discord.Embed(
      title=f"🎲 Prueba de {atributo.capitalize()} ({char[2]})",
      description=(
          f"**D20:** {roll}\n**Atributo:** {attr_val} (Mod. D&D:"
          f" {mod_dnd:+d})\n**Resultado Total:** **{total}**"
      ),
      color=discord.Color.purple(),
  )
  await interaction.response.send_message(embed=embed)


# --- COMANDO EXPLORAR REDISEÑADO CON MAZMORRAS Y PROBABILIDADES ---
@bot.tree.command(
    name="explorar", description="Explora en busca de mazmorras (2/día)"
)
async def explorar(interaction: discord.Interaction):
  user_id = interaction.user.id
  today = datetime.utcnow().strftime("%Y-%m-%d")

  async with aiosqlite.connect(DB_NAME) as db:
    char = await get_active_character(db, user_id)
    if not char:
      return await interaction.response.send_message(
          "🦊 Necesitas un personaje activo y aprobado para explorar.",
          ephemeral=True,
      )

    char_id, str_, agi, explores, last_date = (
        char[0],
        char[10],
        char[12],
        char[17],
        char[18],
    )

    if last_date != today:
      explores = 2

    if explores <= 0:
      return await interaction.response.send_message(
          "🦊 Has agotado tus 2 exploraciones del día. Vuelve mañana.",
          ephemeral=True,
      )

    explores -= 1
    await db.execute(
        "UPDATE characters SET daily_explores = ?, last_daily = ? WHERE id = ?",
        (explores, today, char_id),
    )

    async with db.execute(
        "SELECT modifier FROM abyss_state WHERE id = 1"
    ) as cursor:
      abyss_row = await cursor.fetchone()
      abyss_mod = abyss_row[0] if abyss_row else 0

    await db.commit()

  # Probabilidad de encontrar cueva (50% de probabilidad)
  found_dungeon = random.random() < 0.50

  if not found_dungeon:
    embed = discord.Embed(
        title=f"🌿 Exploración Frustrada ({char[2]})",
        description=(
            "🦊 Has explorado el territorio durante horas pero **no has hallado ninguna entrada a mazmorra**.\n\n"
            f"*Intentos restantes hoy: {explores}*"
        ),
        color=discord.Color.dark_grey(),
    )
    return await interaction.response.send_message(embed=embed)

  # Determinación del Tier por pesos
  tiers = list(DUNGEON_TIERS.keys())
  weights = [DUNGEON_TIERS[t]["weight"] for t in tiers]
  selected_tier_name = random.choices(tiers, weights=weights, k=1)[0]
  selected_tier_info = DUNGEON_TIERS[selected_tier_name]

  view = DungeonExploreView(
      char_id,
      {"fuerza": str_, "agilidad": agi},
      abyss_mod,
      selected_tier_name,
      selected_tier_info,
  )
  embed = discord.Embed(
      title=f"🌿 ¡Entrada a Mazmorra Encontrada! ({char[2]})",
      description=(
          f"🦊 Has localizado una cueva de dificultad **{selected_tier_name}**.\n\n"
          f"🎯 **Dificultad de Desafío (DC):** {selected_tier_info['dc']}\n"
          f"🎒 **Posible Botín:** `{selected_tier_info['loot']}` + Coronas de oro/plata\n\n"
          f"¿Deseas intentar entrar?\n*Intentos restantes hoy: {explores}*"
      ),
      color=discord.Color.dark_blue(),
  )
  await interaction.response.send_message(embed=embed, view=view)


@bot.tree.command(name="clima", description="Muestra el estado del Abismo")
async def clima(interaction: discord.Interaction):
  async with aiosqlite.connect(DB_NAME) as db:
    async with db.execute(
        "SELECT state_name, modifier, weather FROM abyss_state WHERE id = 1"
    ) as cursor:
      row = await cursor.fetchone()

  embed = discord.Embed(
      title="🌌 Estado del Abismo y Clima de Elaris",
      description=(
          f"**Estado del Abismo:** {row[0]} (Modificador:"
          f" {row[1]})\n**Clima:** {row[2]}"
      ),
      color=discord.Color.dark_purple(),
  )
  await interaction.response.send_message(embed=embed)


# --- TIENDAS Y CATÁLOGO ---
class ShopGroup(app_commands.Group):

  @app_commands.command(name="crear", description="Crea tu tienda personal")
  async def crear_tienda(
      self, interaction: discord.Interaction, nombre: str, descripcion: str
  ):
    async with aiosqlite.connect(DB_NAME) as db:
      await db.execute(
          "INSERT OR REPLACE INTO shops (owner_id, name, description) VALUES"
          " (?, ?, ?)",
          (interaction.user.id, nombre, descripcion),
      )
      await db.commit()
    await interaction.response.send_message(
        f"🏪 La tienda **{nombre}** se ha abierto en Elaris."
    )

  @app_commands.command(
      name="producto-crear", description="Añade un producto a tu tienda"
  )
  async def prod_crear(self, interaction: discord.Interaction):
    await interaction.response.send_modal(ProductModal())


bot.tree.add_command(ShopGroup(name="tienda", description="Gestión de tiendas"))


@bot.tree.command(name="catalogo", description="Ver el catálogo de una tienda")
async def catalogo(interaction: discord.Interaction, dueno: discord.User):
  async with aiosqlite.connect(DB_NAME) as db:
    async with db.execute(
        "SELECT name FROM shops WHERE owner_id = ?", (dueno.id,)
    ) as cursor:
      shop_row = await cursor.fetchone()

    if not shop_row:
      return await interaction.response.send_message(
          "🦊 Este usuario no posee una tienda registrada.", ephemeral=True
      )

    async with db.execute(
        "SELECT id, name, description, price, image_url, stock FROM products"
        " WHERE shop_id = ?",
        (dueno.id,),
    ) as cursor:
      products = await cursor.fetchall()

    icons = await get_server_icons(db)

  if not products:
    return await interaction.response.send_message(
        "🦊 Esta tienda no tiene productos en exhibición.", ephemeral=True
    )

  paginator = CatalogPaginator(products, shop_row[0], icons)
  await interaction.response.send_message(
      embed=paginator.build_embed(), view=paginator
  )


# --- EVENTOS Y MISIONES ---
@bot.tree.command(
    name="evento-crear", description="Anuncia un evento rápido con alistamiento"
)
async def evento_crear(
    interaction: discord.Interaction,
    titulo: str,
    descripcion: str,
    dificultad: str,
    max_participantes: int,
    imagen: str = None,
):
  if not await check_command_perm(interaction, "evento-crear"):
    return await interaction.response.send_message(
        "🦊 No tienes permiso para crear eventos.", ephemeral=True
    )

  view = EventJoinView(
      master_name=interaction.user.display_name,
      max_participants=max_participants,
  )
  embed = discord.Embed(
      title=f"📜 EVENTO: {titulo}",
      description=f"{descripcion}\n\n**Dificultad:** {dificultad}",
      color=discord.Color.dark_red(),
  )
  embed.add_field(
      name=f"👥 Participantes (0/{max_participantes})",
      value="Nadie aún.",
      inline=False,
  )
  embed.set_footer(text=f"🧙‍♂️ Master a cargo: {interaction.user.display_name}")

  if imagen and imagen.startswith("http"):
    embed.set_image(url=imagen)

  await interaction.response.send_message(embed=embed, view=view)


@bot.tree.command(
    name="mision-recompensa",
    description="Abre el panel de entrega de recompensas",
)
async def mision_recompensa(interaction: discord.Interaction):
  if not await check_command_perm(interaction, "mision-recompensa"):
    return await interaction.response.send_message(
        "🦊 No posees el rol para entregar recompensas.", ephemeral=True
    )

  view = MissionRewardView(interaction.user)
  await interaction.response.send_message(
      "🦊 **Panel de Misiones**: Configura la recompensa para los"
      " participantes.",
      view=view,
      ephemeral=True,
  )


# --- CONFIGURACIONES ADMINISTRATIVAS ---
@bot.tree.command(
    name="config-iconos", description="Configura los emojis del servidor"
)
@app_commands.checks.has_permissions(administrator=True)
async def config_iconos(interaction: discord.Interaction, tipo: str, emoji: str):
  valid_keys = ["platino", "oro", "plata", "cobre", "copas", "favor"]
  if tipo.lower() not in valid_keys:
    return await interaction.response.send_message(
        f"🦊 Tipo no válido. Opciones: {', '.join(valid_keys)}", ephemeral=True
    )

  async with aiosqlite.connect(DB_NAME) as db:
    await db.execute(
        """
            INSERT INTO custom_icons (key, emoji) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET emoji = ?
        """,
        (tipo.lower(), emoji, emoji),
    )
    await db.commit()

  await interaction.response.send_message(
      f"✨ Icono para **{tipo}** actualizado a {emoji}."
  )


@bot.tree.command(
    name="config-clima-canal", description="Define el canal del clima diario"
)
@app_commands.checks.has_permissions(administrator=True)
async def config_clima_canal(
    interaction: discord.Interaction, canal: discord.TextChannel
):
  async with aiosqlite.connect(DB_NAME) as db:
    await db.execute(
        """
            INSERT INTO weather_config (id, channel_id) VALUES (1, ?)
            ON CONFLICT(id) DO UPDATE SET channel_id = ?
        """,
        (canal.id, canal.id),
    )
    await db.commit()

  await interaction.response.send_message(
      f"🌌 Reporte del clima configurado para enviarse en {canal.mention}."
  )


@bot.tree.command(
    name="config-permisos",
    description="Asigna un rol requerido a un comando específico",
)
@app_commands.checks.has_permissions(administrator=True)
async def config_permisos(
    interaction: discord.Interaction, comando: str, rol: discord.Role
):
  async with aiosqlite.connect(DB_NAME) as db:
    await db.execute(
        """
            INSERT INTO command_permissions (command_name, role_id) VALUES (?, ?)
            ON CONFLICT(command_name) DO UPDATE SET role_id = ?
        """,
        (comando.lower(), rol.id, rol.id),
    )
    await db.commit()

  await interaction.response.send_message(
      f"🔒 Comando `/{comando}` restringido al rol {rol.mention}."
  )


# --- EJECUCIÓN DEL BOT ---
if __name__ == "__main__":
  keep_alive()
  TOKEN = os.environ.get("DISCORD_TOKEN")
  if TOKEN:
    bot.run(TOKEN)
