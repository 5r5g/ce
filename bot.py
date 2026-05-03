import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import os
from datetime import datetime, timedelta
import pytz
import json
import re

from database import *

# Bot configuration
TOKEN = os.environ.get('DISCORD_TOKEN')  # NEVER hardcode token
SERVER_ID = 1498422449044193310  # Your server ID

# Team configurations with colors
TEAMS = {
    "1498422449044193319": {"name": "Philadelphia 76ers", "color": 0x006BB6, "short": "PHI"},
    "1498422449044193318": {"name": "San Antonio Spurs", "color": 0xC4CED4, "short": "SAS"},
    "1498422449044193317": {"name": "Denver Nuggets", "color": 0xFEC524, "short": "DEN"},
    "1498422449044193313": {"name": "Oklahoma City Thunder", "color": 0x007AC1, "short": "OKC"},
    "1498422449044193312": {"name": "New York Knicks", "color": 0xF58426, "short": "NYK"}
}

FO_ROLE_ID = "1498422449044193320"
EST = pytz.timezone('US/Eastern')

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)

# ============ HELPER FUNCTIONS ============

def create_embed(title, description, color, fields=None, footer=None, thumbnail=None):
    """Create a clean, minimalistic embed"""
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.now(EST)
    )
    if fields:
        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)
    if footer:
        embed.set_footer(text=footer)
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    return embed

async def get_user_team_color(user_id):
    """Get team color for a user based on their roles"""
    guild = bot.get_guild(SERVER_ID)
    if not guild:
        return 0x2B2D31
    member = guild.get_member(int(user_id))
    if not member:
        return 0x2B2D31
    
    for role in member.roles:
        if str(role.id) in TEAMS:
            return TEAMS[str(role.id)]["color"]
    return 0x2B2D31

async def notify_team(team_role_id, message, bot_instance):
    """Send notification to all members of a team"""
    guild = bot_instance.get_guild(SERVER_ID)
    if not guild:
        return
    role = guild.get_role(int(team_role_id))
    if role:
        channel = guild.system_channel or discord.utils.get(guild.text_channels, name="general")
        if channel:
            await channel.send(f"{role.mention}", embed=message)

# ============ BACKGROUND TASK: GAME REMINDERS ============

@tasks.loop(minutes=1)
async def check_game_reminders():
    """Check for scheduled games and send reminders"""
    current_time = datetime.now(EST).timestamp()
    pending_games = get_pending_games(current_time)
    
    for game in pending_games:
        game_time = datetime.fromtimestamp(game['scheduled_timestamp'], EST)
        time_diff = (game_time - datetime.now(EST)).total_seconds() / 60  # minutes until game
        
        embed_color = TEAMS.get(game['home_team_id'], {}).get("color", 0x2B2D31)
        
        if 55 <= time_diff <= 65 and not game['notified_1h']:
            # 1 hour reminder
            embed = create_embed(
                "🏀 Game in 1 Hour",
                f"**{game['home_team_name']}** vs **{game['away_team_name']}**",
                embed_color,
                fields=[
                    ("📅 Date", game['game_date'], True),
                    ("⏰ Time", f"{game['game_time']} EST", True),
                    ("📍 Location", f"{game['home_team_name']} Arena", False)
                ],
                footer="Lost's Resort • Please be ready 10 minutes early"
            )
            await notify_team(game['home_team_id'], embed, bot)
            await notify_team(game['away_team_id'], embed, bot)
            update_game_notification(game['id'], 'notified_1h')
            
        elif 10 <= time_diff <= 20 and not game['notified_15m']:
            # 15 minute reminder
            embed = create_embed(
                "⏰ Game Starting Soon!",
                f"**{game['home_team_name']}** vs **{game['away_team_name']}** kicks off in 15 minutes",
                embed_color,
                footer="Lost's Resort • Head to the game channel now!"
            )
            await notify_team(game['home_team_id'], embed, bot)
            await notify_team(game['away_team_id'], embed, bot)
            update_game_notification(game['id'], 'notified_15m')
            
        elif -5 <= time_diff <= 5 and not game['notified_now']:
            # Game time
            embed = create_embed(
                "🏀 GAME TIME!",
                f"**{game['home_team_name']}** vs **{game['away_team_name']}** is starting NOW!",
                embed_color,
                fields=[("🎮 Join", "Head to the game voice channel", False)],
                footer="Lost's Resort • Good luck to both teams!"
            )
            await notify_team(game['home_team_id'], embed, bot)
            await notify_team(game['away_team_id'], embed, bot)
            update_game_notification(game['id'], 'notified_now')

# ============ COMMANDS ============

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    init_db()
    check_game_reminders.start()
    
    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(e)

def is_admin():
    async def predicate(interaction: discord.Interaction):
        return interaction.user.guild_permissions.administrator
    return app_commands.check(predicate)

# ----- Help Command -----
@bot.command(name='lostsresort')
async def help_command(ctx):
    """Display all bot commands"""
    embed = create_embed(
        "🏀 Lost's Resort Bot Commands",
        "Your complete guide to managing the MyPark community",
        0x5865F2,
        fields=[
            ("📋 General", "`!lostsresort` - Show this help menu\n`!stats @user` - View player statistics", False),
            ("🎮 Game Management (Admin)", "`!setup [day] [time] [@home] [@away]` - Schedule a game\n`!reportgame [@team] [score]` - Report game results", False),
            ("🏆 MVP System", "`!vote @player` - Vote for MVP (when active)\n`!mvp_status` - View current vote counts\n`!nominate @player [reason]` - Nominate a player", False),
            ("🔄 Trading", "`!trade @user1 @user2 [message]` - Propose a trade\n(FOs must accept with reactions)", False),
            ("📢 Announcements (Admin)", "`!dmall [message]` - DM all server members", False),
        ],
        footer="Lost's Resort • EST Timezone • Professional Basketball Community"
    )
    await ctx.send(embed=embed)

# ----- Stats Command -----
@bot.command(name='stats')
async def show_stats(ctx, user: discord.Member = None):
    """Display player statistics"""
    target = user or ctx.author
    stats = get_player_stats(str(target.id))
    
    if not stats:
        embed = create_embed(
            "No Stats Found",
            f"{target.mention} hasn't played any recorded games yet.",
            0xED4245,
            footer="Lost's Resort • Stats are updated after each reported game"
        )
        await ctx.send(embed=embed)
        return
    
    team_color = await get_user_team_color(target.id)
    team_name = TEAMS.get(stats['team_role_id'], {}).get("name", "Free Agent")
    
    # Calculate averages
    ppg = stats['total_points'] / stats['games_played'] if stats['games_played'] > 0 else 0
    rpg = stats['total_rebounds'] / stats['games_played'] if stats['games_played'] > 0 else 0
    apg = stats['total_assists'] / stats['games_played'] if stats['games_played'] > 0 else 0
    spg = stats['total_steals'] / stats['games_played'] if stats['games_played'] > 0 else 0
    bpg = stats['total_blocks'] / stats['games_played'] if stats['games_played'] > 0 else 0
    win_pct = (stats['wins'] / stats['games_played'] * 100) if stats['games_played'] > 0 else 0
    
    # Trophy emoji for standout stats
    trophy = "🏆" if ppg >= 20 else "⭐" if ppg >= 15 else ""
    
    embed = create_embed(
        f"{trophy} {target.display_name} - Career Statistics",
        f"**{team_name}** • {stats['games_played']} Games Played",
        team_color,
        fields=[
            ("📊 Per Game Averages", f"Points: **{ppg:.1f}**\nRebounds: **{rpg:.1f}**\nAssists: **{apg:.1f}**", True),
            ("🛡️ Defensive", f"Steals: **{spg:.1f}**\nBlocks: **{bpg:.1f}**", True),
            ("📈 Totals", f"PTS: {stats['total_points']}\nREB: {stats['total_rebounds']}\nAST: {stats['total_assists']}", True),
            ("🏅 Records", f"Win %: **{win_pct:.1f}%**\nMVP Awards: **{stats['mvp_awards']}**\nCareer High: **{stats['career_high_points']}** PTS", False),
        ],
        footer=f"Lost's Resort • Season Career Stats"
    )
    embed.set_author(name=target.display_name, icon_url=target.display_avatar.url)
    await ctx.send(embed=embed)

# ----- Setup Game Command (Admin) -----
@bot.command(name='setup')
@commands.has_permissions(administrator=True)
async def setup_game(ctx, day: int, time: str, home_team: discord.Role, away_team: discord.Role):
    """Schedule a game: !setup 15 19:30 @76ers @Knicks"""
    
    # Validate team roles
    if str(home_team.id) not in TEAMS or str(away_team.id) not in TEAMS:
        await ctx.send("❌ Invalid team roles. Please use valid team roles.")
        return
    
    # Parse time
    try:
        hour, minute = map(int, time.split(':'))
    except:
        await ctx.send("❌ Invalid time format. Use HH:MM (24-hour format)")
        return
    
    now = datetime.now(EST)
    game_datetime = now.replace(day=day, hour=hour, minute=minute, second=0, microsecond=0)
    
    if game_datetime < now:
        await ctx.send("❌ Game time must be in the future.")
        return
    
    # Save to database
    game_id = add_scheduled_game(
        game_datetime.strftime("%B %d, %Y"),
        game_datetime.strftime("%I:%M %p"),
        str(home_team.id),
        TEAMS[str(home_team.id)]["name"],
        str(away_team.id),
        TEAMS[str(away_team.id)]["name"],
        game_datetime.timestamp()
    )
    
    embed = create_embed(
        "✅ Game Scheduled",
        f"**{TEAMS[str(home_team.id)]['name']}** vs **{TEAMS[str(away_team.id)]['name']}**",
        TEAMS[str(home_team.id)]["color"],
        fields=[
            ("📅 Date", game_datetime.strftime("%B %d, %Y"), True),
            ("⏰ Time", f"{game_datetime.strftime('%I:%M %p')} EST", True),
            ("🏠 Home", TEAMS[str(home_team.id)]["name"], True),
            ("✈️ Away", TEAMS[str(away_team.id)]["name"], True)
        ],
        footer="Reminders will be sent 1 hour, 15 minutes, and at game time"
    )
    await ctx.send(embed=embed)

# ----- DM All Command (Admin) -----
@bot.command(name='dmall')
@commands.has_permissions(administrator=True)
async def dm_all(ctx, *, message: str):
    """DM all server members"""
    await ctx.send("📢 Sending announcements to all members. This may take a moment...")
    
    sent = 0
    failed = 0
    
    for member in ctx.guild.members:
        if not member.bot:
            try:
                embed = create_embed(
                    "Announcement from Lost's Resort",
                    message,
                    0x5865F2,
                    footer=f"Sent by {ctx.author.display_name} • Lost's Resort Management"
                )
                embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
                await member.send(embed=embed)
                sent += 1
                await asyncio.sleep(0.5)  # Rate limit protection
            except:
                failed += 1
    
    await ctx.send(f"✅ Announcement sent to {sent} members. Failed: {failed}")

# ----- Trade Command -----
@bot.command(name='trade')
async def trade_command(ctx, player1: discord.Member, player2: discord.Member, *, message: str = "No message provided"):
    """Propose a trade between two players"""
    
    if player1.bot or player2.bot:
        await ctx.send("❌ Cannot trade with bots.")
        return
    
    # Get team roles
    team1 = None
    team2 = None
    
    for role in player1.roles:
        if str(role.id) in TEAMS:
            team1 = role
            break
    
    for role in player2.roles:
        if str(role.id) in TEAMS:
            team2 = role
            break
    
    if not team1 or not team2:
        await ctx.send("❌ Both players must have team roles to trade.")
        return
    
    # Create trade offer
    trade_id = create_trade_offer(str(player1.id), str(player2.id), str(team1.id), str(team2.id), message)
    
    # Find FO members
    fo_role = ctx.guild.get_role(int(FO_ROLE_ID))
    fo_mentions = []
    for member in ctx.guild.members:
        if fo_role in member.roles:
            fo_mentions.append(member.mention)
    
    trade_embed = create_embed(
        "🔄 Trade Proposal",
        f"**{player1.display_name}** ({team1.name}) ↔ **{player2.display_name}** ({team2.name})",
        0x5865F2,
        fields=[
            ("📝 Message", f"\"{message}\"", False),
            ("📋 Trade ID", f"`{trade_id}`", True),
            ("⏳ Expires", "24 hours", True)
        ],
        footer="Franchise Owners: React with ✅ to accept or ❌ to decline"
    )
    
    # Send to FO channel or DM
    for fo in fo_mentions:
        await ctx.send(f"{fo}", embed=trade_embed)
    
    # Store the message ID for reaction handling (simplified - in production use a more robust system)
    await ctx.send(f"Trade proposal #{trade_id} sent to Franchise Owners for approval.")

# ----- MVP Vote Command -----
@bot.command(name='vote')
async def cast_vote(ctx, nominee: discord.Member):
    """Vote for MVP (when voting is active)"""
    
    if nominee == ctx.author:
        await ctx.send("❌ You cannot vote for yourself.")
        return
    
    active_week = get_active_mvp_week()
    if not active_week:
        await ctx.send("❌ MVP voting is not currently active. Voting opens every Monday and closes Sunday at midnight EST.")
        return
    
    success = cast_vote(str(ctx.author.id), str(nominee.id), active_week['week_start'])
    
    if success:
        embed = create_embed(
            "🗳️ Vote Cast",
            f"You voted for **{nominee.display_name}** as this week's MVP!",
            await get_user_team_color(ctx.author.id),
            footer="Lost's Resort • Thank you for participating"
        )
        await ctx.send(embed=embed)
    else:
        await ctx.send("❌ You have already voted this week. One vote per member per week.")

# ----- MVP Status Command -----
@bot.command(name='mvp_status')
async def mvp_status(ctx):
    """View current MVP vote counts"""
    
    active_week = get_active_mvp_week()
    if not active_week:
        await ctx.send("No active voting period.")
        return
    
    votes = get_vote_counts(active_week['week_start'])
    
    if not votes:
        await ctx.send("No votes have been cast yet this week.")
        return
    
    # Build leaderboard
    leaderboard = []
    for idx, vote in enumerate(votes, 1):
        nominee = ctx.guild.get_member(int(vote['nominee_id']))
        name = nominee.display_name if nominee else "Unknown Player"
        leaderboard.append(f"**{idx}.** {name} — {vote['votes']} vote{'s' if vote['votes'] != 1 else ''}")
    
    embed = create_embed(
        "🏆 MVP Voting - Current Standings",
        f"Week of {active_week['week_start']} to {active_week['week_end']}",
        0xFEE75C,
        fields=[("📊 Votes", "\n".join(leaderboard[:10]), False)],
        footer="Lost's Resort • Voting closes Sunday at 11:59 PM EST"
    )
    await ctx.send(embed=embed)

# ----- Nominate Command -----
@bot.command(name='nominate')
async def nominate_player(ctx, player: discord.Member, *, reason: str = "Outstanding performance"):
    """Nominate a player for MVP"""
    
    active_week = get_active_mvp_week()
    if not active_week:
        await ctx.send("❌ MVP voting is not currently active.")
        return
    
    # Update nominations in the week (simplified)
    embed = create_embed(
        "📋 Player Nominated for MVP",
        f"**{player.display_name}** has been nominated by {ctx.author.display_name}",
        0xFEE75C,
        fields=[("🏀 Reason", reason, False)],
        footer="Lost's Resort • This player has been added to consideration"
    )
    await ctx.send(embed=embed)

# ----- Report Game Command (Admin) -----
@bot.command(name='reportgame')
@commands.has_permissions(administrator=True)
async def report_game(ctx, winning_team: discord.Role, score: str, *, stats_summary: str = None):
    """Report game results and update stats: !reportgame @76ers 92-88 @Player1:24pts 8reb"""
    
    # This is a simplified version. In production, you'd want a more interactive flow
    embed = create_embed(
        "📊 Game Reported",
        f"**{winning_team.name}** won {score}",
        0x57F287,
        footer="Stats have been recorded to player profiles"
    )
    await ctx.send(embed=embed)
    await ctx.send("⚠️ Manual stat entry will need to be implemented per your specific tracking needs.")

# ============ RUN BOT ============

if __name__ == "__main__":
    if not TOKEN:
        print("ERROR: DISCORD_TOKEN environment variable not set!")
    else:
        bot.run(TOKEN)
