import sqlite3
from datetime import datetime, timedelta
from contextlib import contextmanager

@contextmanager
def get_db():
    conn = sqlite3.connect('stats.db')
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Player stats table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS player_stats (
                user_id TEXT PRIMARY KEY,
                username TEXT,
                team_role_id TEXT,
                games_played INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                total_points INTEGER DEFAULT 0,
                total_rebounds INTEGER DEFAULT 0,
                total_assists INTEGER DEFAULT 0,
                total_steals INTEGER DEFAULT 0,
                total_blocks INTEGER DEFAULT 0,
                mvp_awards INTEGER DEFAULT 0,
                career_high_points INTEGER DEFAULT 0
            )
        ''')
        
        # Scheduled games table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS scheduled_games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_date TEXT,
                game_time TEXT,
                home_team_id TEXT,
                home_team_name TEXT,
                away_team_id TEXT,
                away_team_name TEXT,
                scheduled_timestamp REAL,
                notified_1h INTEGER DEFAULT 0,
                notified_15m INTEGER DEFAULT 0,
                notified_now INTEGER DEFAULT 0
            )
        ''')
        
        # MVP voting tables
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS mvp_votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                week_start TEXT,
                week_end TEXT,
                voter_id TEXT,
                nominee_id TEXT,
                voted_at REAL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS mvp_week (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                week_start TEXT UNIQUE,
                week_end TEXT,
                is_active INTEGER DEFAULT 1,
                nominations TEXT
            )
        ''')
        
        # Trade offers table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pending_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player1_id TEXT,
                player2_id TEXT,
                team1_id TEXT,
                team2_id TEXT,
                message TEXT,
                status TEXT DEFAULT 'pending',
                created_at REAL
            )
        ''')
        
        conn.commit()

# Player stats operations
def get_player_stats(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM player_stats WHERE user_id = ?', (user_id,))
        return cursor.fetchone()

def update_player_stats(user_id, username, team_role_id, stats):
    with get_db() as conn:
        cursor = conn.cursor()
        existing = get_player_stats(user_id)
        
        if existing:
            cursor.execute('''
                UPDATE player_stats SET
                    username = ?, team_role_id = ?,
                    games_played = games_played + ?,
                    wins = wins + ?, losses = losses + ?,
                    total_points = total_points + ?, total_rebounds = total_rebounds + ?,
                    total_assists = total_assists + ?, total_steals = total_steals + ?,
                    total_blocks = total_blocks + ?,
                    career_high_points = MAX(career_high_points, ?)
                WHERE user_id = ?
            ''', (username, team_role_id, 
                  stats['games'], stats['wins'], stats['losses'],
                  stats['points'], stats['rebounds'], stats['assists'],
                  stats['steals'], stats['blocks'], stats['points'], user_id))
        else:
            cursor.execute('''
                INSERT INTO player_stats 
                (user_id, username, team_role_id, games_played, wins, losses,
                 total_points, total_rebounds, total_assists, total_steals,
                 total_blocks, career_high_points)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, username, team_role_id,
                  stats['games'], stats['wins'], stats['losses'],
                  stats['points'], stats['rebounds'], stats['assists'],
                  stats['steals'], stats['blocks'], stats['points']))

# Game scheduling
def add_scheduled_game(game_date, game_time, home_id, home_name, away_id, away_name, timestamp):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO scheduled_games 
            (game_date, game_time, home_team_id, home_team_name, away_team_id, away_team_name, scheduled_timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (game_date, game_time, home_id, home_name, away_id, away_name, timestamp))
        return cursor.lastrowid

def get_pending_games(current_time):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM scheduled_games 
            WHERE scheduled_timestamp <= ? AND notified_now = 0
            ORDER BY scheduled_timestamp ASC
        ''', (current_time,))
        return cursor.fetchall()

def update_game_notification(game_id, field):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f'UPDATE scheduled_games SET {field} = 1 WHERE id = ?', (game_id,))

# MVP voting
def get_active_mvp_week():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM mvp_week WHERE is_active = 1 ORDER BY id DESC LIMIT 1')
        return cursor.fetchone()

def create_mvp_week(start_date, end_date):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO mvp_week (week_start, week_end, is_active, nominations)
            VALUES (?, ?, 1, ?)
        ''', (start_date, end_date, '[]'))
        return cursor.lastrowid

def close_mvp_week():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE mvp_week SET is_active = 0 WHERE is_active = 1')

def cast_vote(voter_id, nominee_id, week_start):
    with get_db() as conn:
        cursor = conn.cursor()
        # Check if already voted this week
        cursor.execute('''
            SELECT * FROM mvp_votes WHERE voter_id = ? AND week_start = ?
        ''', (voter_id, week_start))
        if cursor.fetchone():
            return False
        cursor.execute('''
            INSERT INTO mvp_votes (week_start, week_end, voter_id, nominee_id, voted_at)
            VALUES (?, (SELECT week_end FROM mvp_week WHERE week_start = ?), ?, ?, ?)
        ''', (week_start, week_start, voter_id, nominee_id, datetime.now().timestamp()))
        return True

def get_vote_counts(week_start):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT nominee_id, COUNT(*) as votes 
            FROM mvp_votes 
            WHERE week_start = ?
            GROUP BY nominee_id
            ORDER BY votes DESC
        ''', (week_start,))
        return cursor.fetchall()

# Trade offers
def create_trade_offer(player1_id, player2_id, team1_id, team2_id, message):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO pending_trades (player1_id, player2_id, team1_id, team2_id, message, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (player1_id, player2_id, team1_id, team2_id, message, datetime.now().timestamp()))
        return cursor.lastrowid

def get_pending_trade(trade_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM pending_trades WHERE id = ? AND status = "pending"', (trade_id,))
        return cursor.fetchone()

def update_trade_status(trade_id, status):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE pending_trades SET status = ? WHERE id = ?', (status, trade_id))

def get_player_team(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT team_role_id FROM player_stats WHERE user_id = ?', (user_id,))
        return cursor.fetchone()
