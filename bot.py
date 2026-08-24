import os
import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
import random
import re
from datetime import datetime

DB_NAME = "elaris_lumen.db"

# --- CONSTANTES Y DICCIONARIOS ---
CLASS_GROWTH = {
    "GUERRERO": {"hp": 25, "fuerza": 3, "defensa": 2, "agilidad": 1, "magia": 0},
    "MAGO":     {"hp": 10, "fuerza": 0, "defensa": 1, "agilidad": 1, "magia": 4},
    "PÍCARO":   {"hp": 15, "fuerza": 2, "defensa": 1, "agilidad": 4, "magia": 1}
}

CRAFTING_RECIPES = {
    "Poción de Vida": {"Mineral de Hierro": 1, "Hongo Abisal": 2},
    "Elixir Astral": {"Fragmento de Alma": 2, "Hierba Curativa": 2}
}

DIFFICULTIES = {
    "Fácil":      {"exp": 100,  "soles": 100,  "copas": 1,  "favor": 0},
    "Normal":     {"exp": 250,  "soles": 250,  "copas": 2,  "favor": 1},
    "Difícil":    {"exp": 500,  "soles": 500,  "copas": 4,  "favor": 2},
    "Épica":      {"exp": 900,  "soles": 900,  "copas": 7,  "favor": 4},
    "Legendaria": {"exp": 1500, "soles": 1500, "copas": 12, "favor": 7}
}

LOOT_TABLE = ["Mineral de Hierro", "Hongo Abisal", "Madera Antigua", "Fragmento de Alma", "Hierba Curativa"]
SLOT_PRICE = 1000  # Costo en Soles por cada slot extra

# --- INICIALIZACIÓN DE BASE DE DATOS ---
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
            daily_explores INTEGER DEFAULT 3,
            last_daily TEXT DEFAULT '',
            is_active INTEGER DEFAULT 0
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

        CREATE TABLE IF NOT EXISTS master_roles (
            role_id INTEGER PRIMARY KEY
        );

        CREATE TABLE IF NOT EXISTS shop_roles (
            role_id INTEGER PRIMARY KEY
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

# --- FUNCIONES AUXILIARES ---
def get_required_exp(level: int) -> int:
    return level * 100

async def get_active_character(db, user_id: int):
    async with db.execute("SELECT * FROM characters WHERE user_id = ? AND is_active = 1", (user_id,)) as cursor:
        return await cursor.fetchone()

async def add_exp_to_character(db, char_id: int, exp_amount: int) -> tuple[bool, int]:
    async with db.execute("SELECT level, exp, character_class, hp, fuerza, defensa, agilidad, magia FROM characters WHERE id = ?", (char_id,)) as cursor:
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
        
        growth = CLASS_GROWTH.get(c_class.upper(), {"hp": 10, "fuerza": 1, "defensa": 1, "agilidad": 1, "magia": 1})
        hp += growth["hp"]
        str_ += growth["fuerza"]
        def_ += growth["defensa"]
        agi += growth["agilidad"]
        mag += growth["magia"]

    await db.execute("""
        UPDATE characters 
        SET level = ?, exp = ?, hp = ?, fuerza = ?, defensa = ?, agilidad = ?, magia = ?
        WHERE id = ?
    """, (level, current_exp, hp, str_, def_, agi, mag, char_id))
    await db.commit()
    
    return leveled_up, level

# --- MODALES Y VISTAS ---
class CharacterModal(discord.ui.Modal, title="Crear Personaje en Elaris"):
    name_input = discord.ui.TextInput(label="Nombre", placeholder="Ej: Ardan", required=True)
    age_input = discord.ui.TextInput(label="Edad", placeholder="Ej: 24", required=True)
    race_input = discord.ui.TextInput(label="Raza", placeholder="Ej: Humano, Elfo...", required=True)
    class_input = discord.ui.TextInput(label="Clase (Guerrero, Mago, Pícaro)", placeholder="Ej: Guerrero", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            age = int(self.age_input.value)
        except ValueError:
            return await interaction.response.send_message("🦊 La edad debe ser un número entero.", ephemeral=True)

        c_class = self.class_input.value.upper()
        if c_class not in CLASS_GROWTH:
            return await interaction.response.send_message("🦊 Clase no válida. Elige entre: Guerrero, Mago o Pícaro.", ephemeral=True)

        async with aiosqlite.connect(DB_NAME) as db:
            # Desactivar personajes anteriores del usuario
            await db.execute("UPDATE characters SET is_active = 0 WHERE user_id = ?", (interaction.user.id,))
            
            # Insertar nuevo personaje como activo
            await db.execute("""
                INSERT INTO characters (user_id, name, age, race, character_class, clan, is_active)
                VALUES (?, ?, ?, ?, ?, 'Sin clan', 1)
            """, (interaction.user.id, self.name_input.value, age, self.race_input.value, c_class))
            await db.commit()

        await interaction.response.send_message(f"🦊 Se ha forjado la alma de **{self.name_input.value}**. Ahora es tu personaje activo.")

class SwitchCharacterSelect(discord.ui.Select):
    def __init__(self, characters):
        options = [
            discord.SelectOption(
                label=f"{char[2]} (Nvl. {char[7]} {char[5]})",
                value=str(char[0]),
                description="Seleccionar como personaje activo"
            ) for char in characters
        ]
        super().__init__(placeholder="Selecciona tu personaje activo...", options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_id = int(self.values[0])
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("UPDATE characters SET is_active = 0 WHERE user_id = ?", (interaction.user.id,))
            await db.execute("UPDATE characters SET is_active = 1 WHERE id = ?", (selected_id,))
            await db.commit()

        await interaction.response.send_message("🦊 Has cambiado de personaje activo correctamente.", ephemeral=True)

class SwitchCharacterView(discord.ui.View):
    def __init__(self, characters):
        super().__init__(timeout=60)
        self.add_item(SwitchCharacterSelect(characters))

class ProductModal(discord.ui.Modal, title="Crear Producto"):
    p_name = discord.ui.TextInput(label="Nombre del Producto", required=True)
    p_desc = discord.ui.TextInput(label="Descripción", style=discord.TextStyle.paragraph, required=True)
    p_price = discord.ui.TextInput(label="Precio (Soles)", required=True)
    p_img = discord.ui.TextInput(label="URL de Imagen", required=False)
    p_stock = discord.ui.TextInput(label="Stock (-1 para infinito)", default="-1", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            price = int(self.p_price.value)
            stock = int(self.p_stock.value)
        except ValueError:
            return await interaction.response.send_message("🦊 El precio y el stock deben ser números.", ephemeral=True)

        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("""
                INSERT INTO products (shop_id, name, description, price, image_url, stock)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (interaction.user.id, self.p_name.value, self.p_desc.value, price, self.p_img.value, stock))
            await db.commit()

        await interaction.response.send_message(f"🏪 Producto **{self.p_name.value}** añadido a tu tienda.")

class CatalogPaginator(discord.ui.View):
    def __init__(self, products, shop_name):
        super().__init__(timeout=120)
        self.products = products
        self.shop_name = shop_name
        self.index = 0

    def build_embed(self) -> discord.Embed:
        item = self.products[self.index]
        embed = discord.Embed(
            title=f"🏪 {self.shop_name}",
            description=f"**{item[1]}**\n\n{item[2]}",
            color=discord.Color.gold()
        )
        embed.add_field(name="Precio", value=f"{item[3]} 🪙", inline=True)
        stock_str = "Infinito" if item[5] == -1 else str(item[5])
        embed.add_field(name="Stock", value=stock_str, inline=True)
        
        if item[4]:
            embed.set_image(url=item[4])
            
        embed.set_footer(text=f"Producto {self.index + 1}/{len(self.products)} | ID: {item[0]}")
        return embed

    @discord.ui.button(label="◀ Anterior", style=discord.ButtonStyle.blurple)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.index > 0:
            self.index -= 1
            await interaction.response.edit_message(embed=self.build_embed(), view=self)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="Siguiente ▶", style=discord.ButtonStyle.blurple)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.index < len(self.products) - 1:
            self.index += 1
            await interaction.response.edit_message(embed=self.build_embed(), view=self)
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
        options=[discord.SelectOption(label=k) for k in DIFFICULTIES.keys()]
    )
    async def select_difficulty(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.selected_difficulty = select.values[0]
        await interaction.response.defer()

    @discord.ui.select(
        cls=discord.ui.UserSelect,
        placeholder="Selecciona los participantes...",
        min_values=1,
        max_values=10
    )
    async def select_users(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        self.selected_users = select.values
        await interaction.response.defer()

    @discord.ui.button(label="Entregar recompensas", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.master_user:
            return await interaction.response.send_message("🦊 No eres el Master de esta sesión.", ephemeral=True)

        if not self.selected_users:
            return await interaction.response.send_message("🦊 Selecciona al menos a un participante.", ephemeral=True)

        rewards = DIFFICULTIES[self.selected_difficulty]
        lvl_msgs = []

        async with aiosqlite.connect(DB_NAME) as db:
            for user in self.selected_users:
                active_char = await get_active_character(db, user.id)
                if active_char:
                    char_id = active_char[0]
                    await db.execute("""
                        UPDATE characters 
                        SET soles = soles + ?, copas = copas + ?, favor_divino = favor_divino + ?
                        WHERE id = ?
                    """, (rewards["soles"], rewards["copas"], rewards["favor"], char_id))

                    leveled_up, new_lvl = await add_exp_to_character(db, char_id, rewards["exp"])
                    if leveled_up:
                        lvl_msgs.append(f"✨ **{active_char[2]}** ({user.display_name}) subió al **Nivel {new_lvl}**!")

            await db.commit()

        embed = discord.Embed(
            title="🌙 Recompensas Entregadas",
            description=f"**Dificultad:** {self.selected_difficulty}\n"
                        f"**Participantes:** {', '.join([u.mention for u in self.selected_users])}\n\n"
                        f"**Recompensa individual:**\n"
                        f"🪙 {rewards['soles']} Soles | 🏆 {rewards['copas']} Copas | 🙏 {rewards['favor']} Favor\n"
                        f"✨ {rewards['exp']} EXP",
            color=discord.Color.purple()
        )
        if lvl_msgs:
            embed.add_field(name="🦊 Subidas de Nivel", value="\n".join(lvl_msgs), inline=False)

        await interaction.response.send_message(embed=embed)
        self.stop()

class DungeonExploreView(discord.ui.View):
    def __init__(self, char_id, stats, abyss_mod):
        super().__init__(timeout=60)
        self.char_id = char_id
        self.stats = stats
        self.abyss_mod = abyss_mod

    @discord.ui.button(label="🗝️ Entrar a la Cueva", style=discord.ButtonStyle.green)
    async def enter_dungeon(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True

        roll = random.randint(1, 20)
        total = roll + max(self.stats["fuerza"], self.stats["agilidad"]) + self.abyss_mod

        if total >= 12:
            found = random.choice(LOOT_TABLE)
            qty = random.randint(1, 2)
            async with aiosqlite.connect(DB_NAME) as db:
                await db.execute("""
                    INSERT INTO inventory (char_id, item_name, quantity)
                    VALUES (?, ?, ?)
                    ON CONFLICT(char_id, item_name) DO UPDATE SET quantity = quantity + ?
                """, (self.char_id, found, qty, qty))
                await db.commit()

            embed = discord.Embed(
                title="🦊 Exploración Exitosa",
                description=f"Superaste las trampas de la cueva.\n\n🎲 Tirada: {roll} | Mod. Abismo: {self.abyss_mod} | Total: **{total}**\n🎒 Botín: `{found} x{qty}`",
                color=discord.Color.green()
            )
        else:
            embed = discord.Embed(
                title="🦊 Derrumbe en la Cueva",
                description=f"Tuviste que escapar corriendo antes de quedar atrapado.\n\n🎲 Tirada: {roll} | Total: **{total}**\n*Lumen te observa divertido desde la salida.*",
                color=discord.Color.red()
            )

        await interaction.response.edit_message(embed=embed, view=self)

# --- CONFIGURACIÓN DEL BOT ---
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    await init_db()
    await bot.tree.sync()
    print(f"🦊 Lumen se ha despertado como {bot.user}")

# --- COMANDOS (CORE) ---
@bot.tree.command(name="lumen", description="Muestra la información de Lumen")
async def lumen_info(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🦊🐾 Lumen, el Zorro Guía de Elaris",
        description=(
            "🦊 Una nueva alma ha llegado. Procura no perderte antes de encontrar tu nombre.\n\n"
            "Camino entre los senderos y sombras de Elaris para asegurarme de que no caigas al Abismo... "
            "o al menos para verlo si ocurre."
        ),
        color=discord.Color.orange()
    )
    embed.set_footer(text="✦ Elaris Roleplay | Usa /ayuda para ver tus opciones.")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="ayuda", description="Lista de comandos disponibles")
async def ayuda(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🦊 Guía de Caminantes de Elaris",
        description="Lumen te muestra las herramientas disponibles para tu travesía:",
        color=discord.Color.gold()
    )
    embed.add_field(name="📜 Personajes", value="`/crear-personaje` | `/mis-personajes` | `/perfil` | `/comprar-slot` | `/clan`", inline=False)
    embed.add_field(name="🪙 Economía y Mochila", value="`/cuenta` | `/daily` | `/pagar` | `/inventario` | `/usar` | `/craftear`", inline=False)
    embed.add_field(name="🎲 Dados y Aventura", value="`/tirar` | `/prueba` | `/explorar` | `/clima`", inline=False)
    embed.add_field(name="🏪 Mercado", value="`/catalogo` | `/tienda crear` | `/tienda producto-crear`", inline=False)

    if interaction.user.guild_permissions.administrator:
        embed.add_field(name="🔮 Administración y Masters", value="`/mision-recompensa` | `/dar-item` | `/evento-crear` | `/master-rol` | `/tienda-rol`", inline=False)

    embed.set_footer(text="🦊 Si te pierdes, recuerda que los dados no mienten.")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# --- COMANDOS (PERSONAJE Y SLOTS) ---
@bot.tree.command(name="crear-personaje", description="Crea un nuevo personaje (Máximo 3 base + 2 adicionales comprados)")
async def crear_personaje(interaction: discord.Interaction):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT COUNT(*) FROM characters WHERE user_id = ?", (interaction.user.id,)) as cursor:
            count = (await cursor.fetchone())[0]

        async with db.execute("SELECT extra_slots FROM character_slots WHERE user_id = ?", (interaction.user.id,)) as cursor:
            slot_row = await cursor.fetchone()
            extra_slots = slot_row[0] if slot_row else 0

        max_allowed = 3 + extra_slots

        if count >= max_allowed:
            return await interaction.response.send_message(
                f"🦊 Has alcanzado el límite de personajes permitido ({count}/{max_allowed}). "
                f"Puedes comprar ranuras adicionales en la tienda usando `/comprar-slot` (Máximo 2 extra).",
                ephemeral=True
            )

    await interaction.response.send_modal(CharacterModal())

@bot.tree.command(name="mis-personajes", description="Lista tus personajes y te permite cambiar el personaje activo")
async def mis_personajes(interaction: discord.Interaction):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT * FROM characters WHERE user_id = ?", (interaction.user.id,)) as cursor:
            chars = await cursor.fetchall()

    if not chars:
        return await interaction.response.send_message("🦊 Aún no has creado ningún personaje. Usa `/crear-personaje`.", ephemeral=True)

    embed = discord.Embed(title="📜 Tu Lista de Personajes", color=discord.Color.dark_gold())
    for char in chars:
        active_tag = " 🌟 **[ACTIVO]**" if char[20] == 1 else ""
        embed.add_field(
            name=f"{char[2]} (Nvl. {char[7]}){active_tag}",
            value=f"**Clase:** {char[5]} | **Raza:** {char[4]} | **Clan:** {char[6]}",
            inline=False
        )

    view = SwitchCharacterView(chars)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

@bot.tree.command(name="comprar-slot", description="Compra 1 ranura adicional de personaje (Coste: 1000 Soles, Máx. 2 extra)")
async def comprar_slot(interaction: discord.Interaction):
    user_id = interaction.user.id
    async with aiosqlite.connect(DB_NAME) as db:
        char = await get_active_character(db, user_id)
        if not char:
            return await interaction.response.send_message("🦊 Necesitas al menos un personaje registrado.", ephemeral=True)

        async with db.execute("SELECT extra_slots FROM character_slots WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            extra_slots = row[0] if row else 0

        if extra_slots >= 2:
            return await interaction.response.send_message("🦊 Ya has comprado el número máximo de ranuras adicionales (2 extra).", ephemeral=True)

        soles = char[13]
        if soles < SLOT_PRICE:
            return await interaction.response.send_message(f"🦊 No tienes suficientes Soles. Necesitas **{SLOT_PRICE} Soles** y posees **{soles}**.", ephemeral=True)

        await db.execute("UPDATE characters SET soles = soles - ? WHERE id = ?", (SLOT_PRICE, char[0]))
        await db.execute("""
            INSERT INTO character_slots (user_id, extra_slots) VALUES (?, 1)
            ON CONFLICT(user_id) DO UPDATE SET extra_slots = extra_slots + 1
        """, (user_id,))
        await db.commit()

    await interaction.response.send_message(f"✨ Has comprado 1 ranura de personaje adicional por **{SLOT_PRICE} Soles**! Ahora puedes crear otro personaje.")

@bot.tree.command(name="perfil", description="Muestra la ficha del personaje activo de un usuario")
async def perfil(interaction: discord.Interaction, usuario: discord.User = None):
    target = usuario or interaction.user
    async with aiosqlite.connect(DB_NAME) as db:
        row = await get_active_character(db, target.id)

    if not row:
        return await interaction.response.send_message("🦊 Esa alma no posee un personaje activo en Elaris.", ephemeral=True)

    name, age, race, c_class, clan = row[2], row[3], row[4], row[5], row[6]
    level, exp = row[7], row[8]
    hp, str_, def_, agi, mag = row[9], row[10], row[11], row[12], row[13]
    soles, copas, favor = row[14], row[15], row[16]

    req_exp = get_required_exp(level)

    embed = discord.Embed(title=f"📜 Ficha de {name}", color=discord.Color.dark_gold())
    embed.add_field(name="General", value=f"**Raza:** {race}\n**Edad:** {age}\n**Clase:** {c_class}\n**Clan:** {clan}", inline=True)
    embed.add_field(name="Progreso", value=f"**Nivel:** {level}\n**EXP:** {exp} / {req_exp}", inline=True)
    embed.add_field(name="Riqueza", value=f"🪙 {soles} Soles\n🏆 {copas} Copas\n🙏 {favor} Favor Divino", inline=True)
    embed.add_field(name="Estadísticas", value=f"❤️ HP: {hp}\n⚔️ Fuerza: {str_}\n🛡️ Defensa: {def_}\n💨 Agilidad: {agi}\n✨ Magia: {mag}", inline=False)
    embed.set_footer(text="🦊 Elaris vela por ti.")
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="clan", description="Cambia el clan de tu personaje activo")
async def set_clan(interaction: discord.Interaction, nuevo_clan: str):
    async with aiosqlite.connect(DB_NAME) as db:
        char = await get_active_character(db, interaction.user.id)
        if not char:
            return await interaction.response.send_message("🦊 No tienes un personaje activo.", ephemeral=True)

        await db.execute("UPDATE characters SET clan = ? WHERE id = ?", (nuevo_clan, char[0]))
        await db.commit()
    await interaction.response.send_message(f"🦊 El clan de **{char[2]}** se ha actualizado a: **{nuevo_clan}**.")

# --- COMANDOS (ECONOMÍA) ---
@bot.tree.command(name="cuenta", description="Muestra las monedas de tu personaje activo")
async def cuenta(interaction: discord.Interaction):
    async with aiosqlite.connect(DB_NAME) as db:
        char = await get_active_character(db, interaction.user.id)

    if not char:
        return await interaction.response.send_message("🦊 No tienes un personaje activo. Usa `/crear-personaje`.", ephemeral=True)

    embed = discord.Embed(
        title=f"💰 Bóveda Personal de {char[2]}",
        description=f"🪙 **Soles:** {char[14]}\n🏆 **Copas:** {char[15]}\n🙏 **Favor Divino:** {char[16]}",
        color=discord.Color.gold()
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="daily", description="Reclama la recompensa diaria para tu personaje activo")
async def daily(interaction: discord.Interaction):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_NAME) as db:
        char = await get_active_character(db, interaction.user.id)
        if not char:
            return await interaction.response.send_message("🦊 No tienes un personaje activo.", ephemeral=True)

        if char[18] == today:
            return await interaction.response.send_message("🦊 Ya has reclamado tus Soles del día. Vuelve mañana.", ephemeral=True)

        await db.execute("UPDATE characters SET soles = soles + 50, last_daily = ? WHERE id = ?", (today, char[0]))
        await db.commit()

    await interaction.response.send_message(f"🦊 Recompensa diaria entregada a **{char[2]}**: **50 Soles** 🪙.")

@bot.tree.command(name="pagar", description="Envía Soles desde tu personaje activo a otro jugador")
async def pagar(interaction: discord.Interaction, destinatario: discord.User, cantidad: int):
    if cantidad <= 0:
        return await interaction.response.send_message("🦊 La cantidad debe ser mayor a 0.", ephemeral=True)
    if destinatario.id == interaction.user.id:
        return await interaction.response.send_message("🦊 No puedes enviarte Soles a ti mismo.", ephemeral=True)

    async with aiosqlite.connect(DB_NAME) as db:
        sender_char = await get_active_character(db, interaction.user.id)
        receiver_char = await get_active_character(db, destinatario.id)

        if not sender_char:
            return await interaction.response.send_message("🦊 No tienes un personaje activo.", ephemeral=True)
        if not receiver_char:
            return await interaction.response.send_message("🦊 El destinatario no tiene un personaje activo.", ephemeral=True)

        if sender_char[14] < cantidad:
            return await interaction.response.send_message("🦊 Tu personaje no posee suficientes Soles.", ephemeral=True)

        await db.execute("UPDATE characters SET soles = soles - ? WHERE id = ?", (cantidad, sender_char[0]))
        await db.execute("UPDATE characters SET soles = soles + ? WHERE id = ?", (cantidad, receiver_char[0]))
        await db.commit()

    await interaction.response.send_message(f"🪙 **{sender_char[2]}** ha transferido **{cantidad} Soles** a **{receiver_char[2]}** ({destinatario.mention}).")

# --- COMANDOS (INVENTARIO) ---
@bot.tree.command(name="inventario", description="Muestra la mochila de tu personaje activo")
async def inventario(interaction: discord.Interaction):
    async with aiosqlite.connect(DB_NAME) as db:
        char = await get_active_character(db, interaction.user.id)
        if not char:
            return await interaction.response.send_message("🦊 No tienes un personaje activo.", ephemeral=True)

        async with db.execute("SELECT item_name, quantity FROM inventory WHERE char_id = ?", (char[0],)) as cursor:
            rows = await cursor.fetchall()

    if not rows:
        return await interaction.response.send_message(f"🦊 La bolsa de **{char[2]}** está vacía.", ephemeral=True)

    items_str = "\n".join([f"• **{item}**: x{qty}" for item, qty in rows])
    embed = discord.Embed(title=f"🎒 Mochila de {char[2]}", description=items_str, color=discord.Color.dark_green())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="usar", description="Consume un objeto del inventario de tu personaje activo")
async def usar(interaction: discord.Interaction, item: str):
    async with aiosqlite.connect(DB_NAME) as db:
        char = await get_active_character(db, interaction.user.id)
        if not char:
            return await interaction.response.send_message("🦊 No tienes un personaje activo.", ephemeral=True)

        async with db.execute("SELECT quantity FROM inventory WHERE char_id = ? AND item_name = ?", (char[0], item)) as cursor:
            row = await cursor.fetchone()

        if not row or row[0] <= 0:
            return await interaction.response.send_message("🦊 No posees ese objeto.", ephemeral=True)

        if row[0] == 1:
            await db.execute("DELETE FROM inventory WHERE char_id = ? AND item_name = ?", (char[0], item))
        else:
            await db.execute("UPDATE inventory SET quantity = quantity - 1 WHERE char_id = ? AND item_name = ?", (char[0], item))
        await db.commit()

    await interaction.response.send_message(f"✨ **{char[2]}** ha utilizado **{item}**.")

@bot.tree.command(name="craftear", description="Combina materiales en el inventario de tu personaje activo")
async def craftear(interaction: discord.Interaction, receta: str):
    if receta not in CRAFTING_RECIPES:
        recetas_list = ", ".join(CRAFTING_RECIPES.keys())
        return await interaction.response.send_message(f"🦊 Receta no encontrada. Disponibles: {recetas_list}", ephemeral=True)

    ingredients = CRAFTING_RECIPES[receta]
    async with aiosqlite.connect(DB_NAME) as db:
        char = await get_active_character(db, interaction.user.id)
        if not char:
            return await interaction.response.send_message("🦊 No tienes un personaje activo.", ephemeral=True)

        for ing, req_qty in ingredients.items():
            async with db.execute("SELECT quantity FROM inventory WHERE char_id = ? AND item_name = ?", (char[0], ing)) as cursor:
                row = await cursor.fetchone()
                if not row or row[0] < req_qty:
                    return await interaction.response.send_message(f"🦊 Te faltan materiales: {ing} (necesitas {req_qty}).", ephemeral=True)

        for ing, req_qty in ingredients.items():
            await db.execute("UPDATE inventory SET quantity = quantity - ? WHERE char_id = ? AND item_name = ?", (req_qty, char[0], ing))

        await db.execute("""
            INSERT INTO inventory (char_id, item_name, quantity)
            VALUES (?, ?, 1)
            ON CONFLICT(char_id, item_name) DO UPDATE SET quantity = quantity + 1
        """, (char[0], receta))
        await db.commit()

    await interaction.response.send_message(f"🛠️ **{char[2]}** ha fabricado con éxito: **{receta}**.")

@bot.tree.command(name="dar-item", description="Otorga un ítem al personaje activo de un jugador (Master/Admin)")
async def dar_item(interaction: discord.Interaction, usuario: discord.User, item: str, cantidad: int):
    if cantidad <= 0:
        return await interaction.response.send_message("🦊 La cantidad debe ser positiva.", ephemeral=True)

    async with aiosqlite.connect(DB_NAME) as db:
        char = await get_active_character(db, usuario.id)
        if not char:
            return await interaction.response.send_message("🦊 El objetivo no tiene un personaje activo.", ephemeral=True)

        await db.execute("""
            INSERT INTO inventory (char_id, item_name, quantity)
            VALUES (?, ?, ?)
            ON CONFLICT(char_id, item_name) DO UPDATE SET quantity = quantity + ?
        """, (char[0], item, cantidad, cantidad))
        await db.commit()

    await interaction.response.send_message(f"🎒 Entregado `{item} x{cantidad}` al personaje **{char[2]}** de {usuario.mention}.")

# --- COMANDOS (DADOS) ---
@bot.tree.command(name="tirar", description="Lanza dados (Ejemplo: 1d20+3, 2d6)")
async def tirar(interaction: discord.Interaction, formula: str):
    match = re.match(r"^(\d+)d(\d+)(?:([+-])(\d+))?$", formula.lower().strip())
    if not match:
        return await interaction.response.send_message("🦊 Formato inválido. Usa la notación: 1d20, 2d6+2, etc.", ephemeral=True)

    num_dice = int(match.group(1))
    sides = int(match.group(2))
    sign = match.group(3)
    mod = int(match.group(4)) if match.group(4) else 0

    if num_dice > 20 or sides > 100:
        return await interaction.response.send_message("🦊 Demasiados dados o caras.", ephemeral=True)

    rolls = [random.randint(1, sides) for _ in range(num_dice)]
    raw_total = sum(rolls)
    final_total = raw_total + mod if sign == "+" else raw_total - mod if sign == "-" else raw_total

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
        description=f"**Fórmula:** `{formula}`\n**Resultados:** `[{rolls_str}]`{mod_str}\n**Total:** **{final_total}**{crit_msg}",
        color=discord.Color.blue()
    )
    embed.set_footer(text="🦊 El destino acaba de lanzar los dados.")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="prueba", description="Prueba de atributo utilizando las estadísticas de tu personaje activo")
async def prueba(interaction: discord.Interaction, atributo: str):
    attr = atributo.lower().strip()
    if attr not in ["fuerza", "defensa", "agilidad", "magia"]:
        return await interaction.response.send_message("🦊 Atributos permitidos: Fuerza, Defensa, Agilidad, Magia.", ephemeral=True)

    async with aiosqlite.connect(DB_NAME) as db:
        char = await get_active_character(db, interaction.user.id)
        if not char:
            return await interaction.response.send_message("🦊 No tienes un personaje activo.", ephemeral=True)

        attr_index = {"fuerza": 10, "defensa": 11, "agilidad": 12, "magia": 13}[attr]
        attr_val = char[attr_index]

    roll = random.randint(1, 20)
    total = roll + attr_val

    embed = discord.Embed(
        title=f"🎲 Prueba de {atributo.capitalize()} ({char[2]})",
        description=f"**D20:** {roll}\n**{atributo.capitalize()}:** +{attr_val}\n**Resultado:** **{total}**",
        color=discord.Color.purple()
    )
    await interaction.response.send_message(embed=embed)

# --- COMANDOS (TIENDAS / SHOP) ---
class ShopGroup(app_commands.Group):
    @app_commands.command(name="crear", description="Crea tu tienda personal")
    async def crear_tienda(self, interaction: discord.Interaction, nombre: str, descripcion: str):
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("INSERT OR REPLACE INTO shops (owner_id, name, description) VALUES (?, ?, ?)",
                             (interaction.user.id, nombre, descripcion))
            await db.commit()
        await interaction.response.send_message(f"🏪 La tienda **{nombre}** se ha abierto en Elaris.")

    @app_commands.command(name="producto-crear", description="Añade un producto a tu tienda")
    async def prod_crear(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ProductModal())

bot.tree.add_command(ShopGroup(name="tienda", description="Gestión de tiendas"))

@bot.tree.command(name="catalogo", description="Ver el catálogo de una tienda")
async def catalogo(interaction: discord.Interaction, dueno: discord.User):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT name FROM shops WHERE owner_id = ?", (dueno.id,)) as cursor:
            shop_row = await cursor.fetchone()
        
        if not shop_row:
            return await interaction.response.send_message("🦊 Este usuario no posee una tienda registrada.", ephemeral=True)

        async with db.execute("SELECT id, name, description, price, image_url, stock FROM products WHERE shop_id = ?", (dueno.id,)) as cursor:
            products = await cursor.fetchall()

    if not products:
        return await interaction.response.send_message("🦊 Esta tienda no tiene productos en exhibición.", ephemeral=True)

    paginator = CatalogPaginator(products, shop_row[0])
    await interaction.response.send_message(embed=paginator.build_embed(), view=paginator)

# --- COMANDOS (MISIONES Y EVENTOS) ---
@bot.tree.command(name="mision-recompensa", description="Abre el panel de entrega de recompensas")
async def mision_recompensa(interaction: discord.Interaction):
    view = MissionRewardView(interaction.user)
    await interaction.response.send_message("🦊 **Panel de Misiones**: Configura la recompensa para los participantes.", view=view, ephemeral=True)

@bot.tree.command(name="evento-crear", description="Anuncia un evento rápido para aventureros")
async def evento_crear(interaction: discord.Interaction, titulo: str, descripcion: str, dificultad: str, participantes: str, imagen: str = None):
    embed = discord.Embed(
        title=f"📜 EVENTO: {titulo}",
        description=f"{descripcion}\n\n**Dificultad:** {dificultad}\n**Aventureros convocados:** {participantes}",
        color=discord.Color.dark_red()
    )
    if imagen:
        embed.set_image(url=imagen)
    embed.set_footer(text=f"Master a cargo: {interaction.user.display_name}")
    await interaction.response.send_message(content=f"🚨 {participantes}", embed=embed)

# --- COMANDOS (PERMISOS) ---
@bot.tree.command(name="master-rol", description="Gestiona los roles de Master")
@app_commands.checks.has_permissions(administrator=True)
async def master_rol(interaction: discord.Interaction, accion: str, rol: discord.Role):
    async with aiosqlite.connect(DB_NAME) as db:
        if accion.lower() == "agregar":
            await db.execute("INSERT OR IGNORE INTO master_roles (role_id) VALUES (?)", (rol.id,))
            msg = f"🦊 Rol {rol.mention} añadido como Master."
        elif accion.lower() == "quitar":
            await db.execute("DELETE FROM master_roles WHERE role_id = ?", (rol.id,))
            msg = f"🦊 Rol {rol.mention} removido de Masters."
        else:
            msg = "🦊 Acción no válida (usa `agregar` o `quitar`)."
        await db.commit()

    await interaction.response.send_message(msg, ephemeral=True)

@bot.tree.command(name="tienda-rol", description="Gestiona los roles autorizados para abrir tienda")
@app_commands.checks.has_permissions(administrator=True)
async def tienda_rol(interaction: discord.Interaction, accion: str, rol: discord.Role):
    async with aiosqlite.connect(DB_NAME) as db:
        if accion.lower() == "agregar":
            await db.execute("INSERT OR IGNORE INTO shop_roles (role_id) VALUES (?)", (rol.id,))
            msg = f"🦊 Rol {rol.mention} autorizado para tiendas."
        elif accion.lower() == "quitar":
            await db.execute("DELETE FROM shop_roles WHERE role_id = ?", (rol.id,))
            msg = f"🦊 Rol {rol.mention} revocado de tiendas."
        else:
            msg = "🦊 Acción no válida (usa `agregar` o `quitar`)."
        await db.commit()

    await interaction.response.send_message(msg, ephemeral=True)

# --- COMANDOS (EXPLORACIÓN) ---
@bot.tree.command(name="clima", description="Muestra el estado del Abismo y del clima de hoy")
async def clima(interaction: discord.Interaction):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT state_name, modifier, weather FROM abyss_state WHERE id = 1") as cursor:
            row = await cursor.fetchone()

    embed = discord.Embed(
        title="🌌 Estado del Abismo y Clima de Elaris",
        description=f"**Estado del Abismo:** {row[0]} (Modificador: {row[1]})\n**Clima:** {row[2]}",
        color=discord.Color.dark_purple()
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="explorar", description="Explora zonas en busca de materiales con tu personaje activo (3/día)")
async def explorar(interaction: discord.Interaction):
    user_id = interaction.user.id
    today = datetime.utcnow().strftime("%Y-%m-%d")

    async with aiosqlite.connect(DB_NAME) as db:
        char = await get_active_character(db, user_id)
        if not char:
            return await interaction.response.send_message("🦊 Necesitas un personaje activo para explorar.", ephemeral=True)

        char_id, str_, agi, explores, last_date = char[0], char[10], char[12], char[17], char[18]

        if last_date != today:
            explores = 3

        if explores <= 0:
            return await interaction.response.send_message("🦊 Has agotado tus 3 exploraciones del día para este personaje. Vuelve mañana.", ephemeral=True)

        explores -= 1
        await db.execute("UPDATE characters SET daily_explores = ?, last_daily = ? WHERE id = ?", (explores, today, char_id))

        async with db.execute("SELECT modifier FROM abyss_state WHERE id = 1") as cursor:
            abyss_row = await cursor.fetchone()
            abyss_mod = abyss_row[0] if abyss_row else 0

        await db.commit()

    view = DungeonExploreView(char_id, {"fuerza": str_, "agilidad": agi}, abyss_mod)
    embed = discord.Embed(
        title=f"🌿 Entrada a la Cueva Olvidada ({char[2]})",
        description=f"🦊 Has encontrado una cueva. ¿Deseas adentrarte?\n*Intentos restantes hoy: {explores}*",
        color=discord.Color.dark_blue()
    )
    await interaction.response.send_message(embed=embed, view=view)

# --- EJECUCIÓN DEL BOT ---
if __name__ == "__main__":
    TOKEN = os.environ.get("DISCORD_TOKEN")
