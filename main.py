import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import Modal, TextInput, View, Button
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import random
import json
import os

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

CONFIG_FILE = "captcha_config.json"

if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "r") as f:
        config = json.load(f)
else:
    config = {}

def save_config():
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

def generate_captcha(length: int) -> str:
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "".join(random.choice(chars) for _ in range(length)).upper()

def generate_captcha_image(text: str):
    width, height = 260, 100
    background_color = (240, 240, 240)
    img = Image.new("RGB", (width, height), color=background_color)
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype("font.ttf", 40)

    for _ in range(30):
        start = (random.randint(0, width), random.randint(0, height))
        end = (random.randint(0, width), random.randint(0, height))
        color = tuple(random.randint(140, 210) for _ in range(3))
        draw.line([start, end], fill=color, width=random.randint(1, 2))

    for _ in range(500):
        x, y = random.randint(0, width - 1), random.randint(0, height - 1)
        r = random.choice([0, 1, 2])
        color = tuple(random.randint(0, 255) for _ in range(3))
        if r == 0:
            draw.point((x, y), fill=color)
        else:
            draw.ellipse([x-r, y-r, x+r, y+r], fill=color)

    bbox = draw.textbbox((0, 0), text, font=font)
    total_w = bbox[2] - bbox[0]
    total_h = bbox[3] - bbox[1]
    x_start = int((width - total_w) / 2)
    y_start = int((height - total_h) / 2)

    for char in text:
        char_color = tuple(random.randint(0, 55) for _ in range(3))
        draw.text((x_start, y_start), char, font=font, fill=char_color)

        char_bbox = draw.textbbox((0, 0), char, font=font)
        char_width = char_bbox[2] - char_bbox[0]
        x_start += char_width

    for _ in range(12):
        x0, y0 = random.randint(0, width - 1), random.randint(0, height - 1)
        x1, y1 = random.randint(0, width - 1), random.randint(0, height - 1)
        x0, x1 = min(x0, x1), max(x0, x1)
        y0, y1 = min(y0, y1), max(y0, y1)
        if x1 - x0 < 10: x1 = min(width - 1, x0 + 10)
        if y1 - y0 < 10: y1 = min(height - 1, y0 + 10)
        start = random.randint(0, 360)
        end = (start + random.randint(20, 340)) % 360
        arc_color = tuple(random.randint(90, 200) for _ in range(3))
        try:
            draw.arc([x0, y0, x1, y1], start=start, end=end, fill=arc_color, width=random.randint(1, 2))
        except Exception:
            pass

    for _ in range(10):
        start = (random.randint(0, width), random.randint(0, height))
        end = (random.randint(0, width), random.randint(0, height))
        color = tuple(random.randint(80, 170) for _ in range(3))
        draw.line([start, end], fill=color, width=random.randint(1, 3))

    file = BytesIO()
    img.save(file, format="PNG")
    file.seek(0)
    return file

@bot.tree.command(name="setup", description="Setup Captcha for this server")
@app_commands.describe(length="Captcha length (1-6)", verified_role="Role for verified users")
async def setup(interaction: discord.Interaction, length: int, verified_role: discord.Role):
    if not interaction.guild:
        await interaction.response.send_message("This command can only be used on a server.", ephemeral=True)
        return
    if length < 1 or length > 6:
        await interaction.response.send_message("Length must be between 1 and 6.", ephemeral=True)
        return
    config[str(interaction.guild.id)] = {
        "length": length,
        "role_id": verified_role.id
    }
    save_config()
    await interaction.response.send_message(f"Captcha setup saved for **{interaction.guild.name}** (length {length}).", ephemeral=True)

class CaptchaModal(Modal, title="Captcha"):
    def __init__(self, user: discord.Member, code: str, role: discord.Role):
        super().__init__()
        self.user = user
        self.correct_code = code.upper()
        self.role = role
        self.add_item(TextInput(label="Code", placeholder="Here", max_length=len(code)))

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("You are not allowed to solve this captcha.", ephemeral=True)
            return

        user_input = self.children[0].value.strip().upper()
        if user_input == self.correct_code:
            try:
                await self.user.add_roles(self.role)
            except Exception:
                await interaction.response.send_message("Error: Bot lacks permission to assign the role.", ephemeral=True)
                return
            try:
                await interaction.response.edit_message(content="✅ Captcha completed!", attachments=[], view=None)
            except Exception:
                await interaction.response.send_message("✅ Captcha completed!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Wrong code — try again.", ephemeral=True)

@bot.tree.command(name="captcha", description="Start Captcha")
async def captcha(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message("This command can only be used on a server.", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)
    if guild_id not in config:
        await interaction.response.send_message("Server is not set up. Admin must run `/setup` first.", ephemeral=True)
        return

    guild_conf = config[guild_id]
    role = interaction.guild.get_role(guild_conf.get("role_id"))
    length = guild_conf.get("length", 4)

    if role is None:
        await interaction.response.send_message("Configured role not found. Admin must run /setup again.", ephemeral=True)
        return

    if role in interaction.user.roles:
        await interaction.response.send_message("You already completed the captcha!", ephemeral=True)
        return

    code = generate_captcha(length)
    image_file = generate_captcha_image(code)

    view = View()
    button = Button(label="Enter Code", style=discord.ButtonStyle.primary)

    async def button_callback(btn_interaction: discord.Interaction):
        if btn_interaction.user.id != interaction.user.id:
            await btn_interaction.response.send_message("Only the user who requested the captcha can open this modal.", ephemeral=True)
            return
        await btn_interaction.response.send_modal(CaptchaModal(interaction.user, code, role))

    button.callback = button_callback
    view.add_item(button)

    await interaction.response.send_message(file=discord.File(fp=image_file, filename="captcha.png"),
                                            view=view, ephemeral=True)
@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"Slash Commands synced: {len(synced)} commands")
    except Exception as e:
        print(f"Error during sync: {e}")
    await bot.change_presence(status=discord.Status.dnd, activity=discord.Activity(type=discord.ActivityType.listening, name="made by shinrai"))
    print(f"Bot is online as {bot.user}")

bot.run("")
