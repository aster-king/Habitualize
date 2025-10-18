from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from datetime import datetime, timedelta
import csv
import os
from functools import wraps
from github import Github, InputGitAuthor
import time

app = Flask(__name__)
app.secret_key = 'habitualize-secret-key-change-this-in-production'

# GitHub Configuration
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
GITHUB_REPO = os.environ.get('GITHUB_REPO')  # Format: "username/repo-name"
GITHUB_BRANCH = os.environ.get('GITHUB_BRANCH', 'main')

# CSV Files
HABITS_FILE = 'habits.csv'
COMPLETED_FILE = 'completed.csv'
PROGRESS_LOG_FILE = 'progress_log.csv'
GOALS_FILE = 'goals.csv'

# Initialize GitHub
github_client = None
github_repo = None

if GITHUB_TOKEN and GITHUB_REPO:
    try:
        github_client = Github(GITHUB_TOKEN)
        github_repo = github_client.get_repo(GITHUB_REPO)
        print(f"✅ Connected to GitHub repo: {GITHUB_REPO}")
    except Exception as e:
        print(f"⚠️ GitHub connection failed: {e}")

# GitHub Sync Functions
def sync_file_from_github(file_path):
    """Download file from GitHub to local filesystem"""
    if not github_repo:
        return False
    
    try:
        contents = github_repo.get_contents(file_path, ref=GITHUB_BRANCH)
        with open(file_path, 'wb') as f:
            f.write(contents.decoded_content)
        print(f"✅ Downloaded {file_path} from GitHub")
        return True
    except Exception as e:
        print(f"⚠️ Could not download {file_path}: {e}")
        return False

def sync_file_to_github(file_path, commit_message="Update data"):
    """Upload file from local filesystem to GitHub"""
    if not github_repo:
        print("⚠️ GitHub not configured")
        return False
    
    try:
        # Read local file
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check if file exists in GitHub
        try:
            file_contents = github_repo.get_contents(file_path, ref=GITHUB_BRANCH)
            # File exists - update it
            github_repo.update_file(
                file_path,
                commit_message,
                content,
                file_contents.sha,
                branch=GITHUB_BRANCH
            )
            print(f"✅ Updated {file_path} in GitHub")
        except:
            # File doesn't exist - create it
            github_repo.create_file(
                file_path,
                commit_message,
                content,
                branch=GITHUB_BRANCH
            )
            print(f"✅ Created {file_path} in GitHub")
        
        return True
    except Exception as e:
        print(f"❌ Failed to sync {file_path} to GitHub: {e}")
        return False

# Initialize CSV files
def init_files():
    """Initialize CSV files - download from GitHub or create new"""
    files = {
        HABITS_FILE: ['name', 'points', 'archived', 'creation_date'],
        COMPLETED_FILE: ['date', 'name'],
        PROGRESS_LOG_FILE: ['date', 'earned_points', 'possible_points'],
        GOALS_FILE: ['name', 'status', 'deadline', 'points']
    }
    
    for file_path, headers in files.items():
        # Try to download from GitHub first
        if not sync_file_from_github(file_path):
            # If not in GitHub, create locally
            if not os.path.exists(file_path):
                with open(file_path, 'w', newline='', encoding='utf-8') as f:
                    csv.writer(f).writerow(headers)
                print(f"✅ Created {file_path} locally")
                # Upload to GitHub
                sync_file_to_github(file_path, f"Initialize {file_path}")

# Data Access Functions (Modified to sync with GitHub)
def get_all_habits(archived=None):
    sync_file_from_github(HABITS_FILE)  # Always get latest from GitHub
    
    if not os.path.exists(HABITS_FILE):
        return []
    
    with open(HABITS_FILE, 'r', newline='', encoding='utf-8') as f:
        habits = list(csv.DictReader(f))
    
    if archived is None:
        return habits
    
    return [h for h in habits if (h.get('archived', 'False') == 'True') == archived]

def get_all_goals():
    sync_file_from_github(GOALS_FILE)
    
    if not os.path.exists(GOALS_FILE):
        return []
    
    with open(GOALS_FILE, 'r', newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))

def get_completed_for_date(date_str):
    sync_file_from_github(COMPLETED_FILE)
    
    if not os.path.exists(COMPLETED_FILE):
        return set()
    
    completed = set()
    with open(COMPLETED_FILE, 'r', newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if row.get('date') == date_str:
                completed.add(row.get('name'))
    return completed

def add_habit(name, points):
    creation_date = datetime.now().strftime('%Y-%m-%d')
    with open(HABITS_FILE, 'a', newline='', encoding='utf-8') as f:
        csv.writer(f).writerow([name, points, 'False', creation_date])
    
    # Sync to GitHub
    sync_file_to_github(HABITS_FILE, f"Add habit: {name}")

def update_habit(old_name, new_name, new_points):
    habits = get_all_habits()
    
    if old_name.lower() != new_name.lower():
        if any(h['name'].lower() == new_name.lower() for h in habits):
            return False
    
    for habit in habits:
        if habit['name'] == old_name:
            habit['name'] = new_name
            habit['points'] = str(new_points)
            break
    
    with open(HABITS_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['name', 'points', 'archived', 'creation_date'])
        writer.writeheader()
        writer.writerows(habits)
    
    # Sync to GitHub
    sync_file_to_github(HABITS_FILE, f"Update habit: {old_name} → {new_name}")
    return True

def set_habit_archived(name, is_archived):
    habits = get_all_habits()
    
    for habit in habits:
        if habit['name'] == name:
            habit['archived'] = str(is_archived)
            break
    
    with open(HABITS_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['name', 'points', 'archived', 'creation_date'])
        writer.writeheader()
        writer.writerows(habits)
    
    # Sync to GitHub
    action = "Archive" if is_archived else "Unarchive"
    sync_file_to_github(HABITS_FILE, f"{action} habit: {name}")

def delete_habit(name):
    habits = [h for h in get_all_habits() if h['name'] != name]
    
    with open(HABITS_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['name', 'points', 'archived', 'creation_date'])
        writer.writeheader()
        writer.writerows(habits)
    
    # Also remove from completed records
    if os.path.exists(COMPLETED_FILE):
        with open(COMPLETED_FILE, 'r', newline='', encoding='utf-8') as f:
            records = [r for r in csv.DictReader(f) if r.get('name') != name]
        
        with open(COMPLETED_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['date', 'name'])
            writer.writeheader()
            writer.writerows(records)
        
        sync_file_to_github(COMPLETED_FILE, f"Remove completed records for: {name}")
    
    # Sync to GitHub
    sync_file_to_github(HABITS_FILE, f"Delete habit: {name}")

def toggle_completion(habit_name, is_completed, date_str=None):
    if date_str is None:
        date_str = datetime.now().strftime('%Y-%m-%d')
    
    records = []
    if os.path.exists(COMPLETED_FILE):
        with open(COMPLETED_FILE, 'r', newline='', encoding='utf-8') as f:
            records = [r for r in csv.DictReader(f) 
                      if not (r.get('date') == date_str and r.get('name') == habit_name)]
    
    if is_completed:
        records.append({'date': date_str, 'name': habit_name})
    
    with open(COMPLETED_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['date', 'name'])
        writer.writeheader()
        writer.writerows(records)
    
    # Sync to GitHub
    action = "Complete" if is_completed else "Uncomplete"
    sync_file_to_github(COMPLETED_FILE, f"{action} habit: {habit_name} on {date_str}")

def add_goal(name, status, deadline, points):
    with open(GOALS_FILE, 'a', newline='', encoding='utf-8') as f:
        csv.writer(f).writerow([name, status, deadline, points])
    
    # Sync to GitHub
    sync_file_to_github(GOALS_FILE, f"Add goal: {name}")

def update_goal(old_name, new_name, new_status, new_deadline, new_points):
    goals = get_all_goals()
    
    if old_name.lower() != new_name.lower():
        if any(g['name'].lower() == new_name.lower() for g in goals):
            return False
    
    for goal in goals:
        if goal['name'] == old_name:
            goal['name'] = new_name
            goal['status'] = new_status
            goal['deadline'] = new_deadline
            goal['points'] = str(new_points)
            break
    
    with open(GOALS_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['name', 'status', 'deadline', 'points'])
        writer.writeheader()
        writer.writerows(goals)
    
    # Sync to GitHub
    sync_file_to_github(GOALS_FILE, f"Update goal: {old_name} → {new_name}")
    return True

def delete_goal(name):
    goals = [g for g in get_all_goals() if g['name'] != name]
    
    with open(GOALS_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['name', 'status', 'deadline', 'points'])
        writer.writeheader()
        writer.writerows(goals)
    
    # Sync to GitHub
    sync_file_to_github(GOALS_FILE, f"Delete goal: {name}")

def get_weekly_streak(habit_name):
    today = datetime.now()
    streak = []
    
    for i in range(6, -1, -1):
        date = today - timedelta(days=i)
        date_str = date.strftime('%Y-%m-%d')
        completed = habit_name in get_completed_for_date(date_str)
        streak.append({
            'date': date_str,
            'day': date.strftime('%a'),
            'completed': completed,
            'is_today': i == 0
        })
    
    return streak

def save_progress_snapshot(date_str, earned, possible):
    sync_file_from_github(PROGRESS_LOG_FILE)
    
    records = []
    found = False
    
    if os.path.exists(PROGRESS_LOG_FILE):
        with open(PROGRESS_LOG_FILE, 'r', newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                if row.get('date') == date_str:
                    row['earned_points'] = str(earned)
                    row['possible_points'] = str(possible)
                    found = True
                records.append(row)
    
    if not found:
        records.append({
            'date': date_str,
            'earned_points': str(earned),
            'possible_points': str(possible)
        })
    
    with open(PROGRESS_LOG_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['date', 'earned_points', 'possible_points'])
        writer.writeheader()
        writer.writerows(records)
    
    # Sync to GitHub
    sync_file_to_github(PROGRESS_LOG_FILE, f"Update progress for {date_str}")

def get_progress_snapshot(date_str):
    sync_file_from_github(PROGRESS_LOG_FILE)
    
    if not os.path.exists(PROGRESS_LOG_FILE):
        return None
    
    with open(PROGRESS_LOG_FILE, 'r', newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if row.get('date') == date_str:
                return row
    return None

# Routes (keep all your existing routes from before)
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/daily-overview', methods=['GET'])
def api_daily_overview():
    today_str = datetime.now().strftime('%Y-%m-%d')
    habits = get_all_habits(archived=False)
    completed = get_completed_for_date(today_str)
    
    total_points = 0
    earned_points = 0
    habits_data = []
    
    for habit in habits:
        points = int(habit.get('points', 0))
        total_points += points
        is_completed = habit['name'] in completed
        
        if is_completed:
            earned_points += points
        
        habits_data.append({
            'name': habit['name'],
            'points': points,
            'completed': is_completed,
            'creation_date': habit.get('creation_date', '')
        })
    
    save_progress_snapshot(today_str, earned_points, total_points)
    
    return jsonify({
        'habits': habits_data,
        'total_points': total_points,
        'earned_points': earned_points,
        'percentage': int((earned_points / total_points * 100) if total_points > 0 else 0)
    })

@app.route('/api/habits/toggle', methods=['POST'])
def api_toggle_habit():
    data = request.json
    habit_name = data.get('name')
    is_completed = data.get('completed', False)
    
    toggle_completion(habit_name, is_completed)
    return jsonify({'success': True})

@app.route('/api/habits', methods=['POST'])
def api_add_habit():
    data = request.json
    name = data.get('name', '').strip()
    points = int(data.get('points', 0))
    
    if not name:
        return jsonify({'error': 'Name required'}), 400
    
    if any(h['name'].lower() == name.lower() for h in get_all_habits()):
        return jsonify({'error': 'Habit already exists'}), 400
    
    add_habit(name, points)
    return jsonify({'success': True})

@app.route('/api/habits/update', methods=['POST'])
def api_update_habit():
    data = request.json
    old_name = data.get('old_name')
    new_name = data.get('new_name', '').strip()
    new_points = int(data.get('new_points', 0))
    
    if not new_name:
        return jsonify({'error': 'Name required'}), 400
    
    if update_habit(old_name, new_name, new_points):
        return jsonify({'success': True})
    else:
        return jsonify({'error': 'Habit name already exists'}), 400

@app.route('/api/habits/archive', methods=['POST'])
def api_archive_habit():
    data = request.json
    name = data.get('name')
    is_archived = data.get('archived', True)
    
    set_habit_archived(name, is_archived)
    return jsonify({'success': True})

@app.route('/api/habits/delete', methods=['POST'])
def api_delete_habit():
    data = request.json
    name = data.get('name')
    
    delete_habit(name)
    return jsonify({'success': True})

@app.route('/api/habits/all', methods=['GET'])
def api_all_habits():
    active = get_all_habits(archived=False)
    archived = get_all_habits(archived=True)
    
    return jsonify({
        'active': active,
        'archived': archived
    })

@app.route('/api/habits/streak/<habit_name>', methods=['GET'])
def api_habit_streak(habit_name):
    streak = get_weekly_streak(habit_name)
    return jsonify({'streak': streak})

@app.route('/api/goals', methods=['GET'])
def api_get_goals():
    goals = get_all_goals()
    
    completed_pts = 0
    in_progress_pts = 0
    not_started_pts = 0
    
    for goal in goals:
        points = int(goal.get('points', 0))
        status = goal.get('status', 'Not Started')
        
        if status == 'Completed':
            completed_pts += points
        elif status == 'In Progress':
            in_progress_pts += points
        else:
            not_started_pts += points
    
    return jsonify({
        'goals': goals,
        'stats': {
            'completed': completed_pts,
            'in_progress': in_progress_pts,
            'not_started': not_started_pts,
            'total': completed_pts + in_progress_pts + not_started_pts
        }
    })

@app.route('/api/goals', methods=['POST'])
def api_add_goal():
    data = request.json
    name = data.get('name', '').strip()
    status = data.get('status', 'Not Started')
    deadline = data.get('deadline', '')
    points = int(data.get('points', 0))
    
    if not name:
        return jsonify({'error': 'Name required'}), 400
    
    if any(g['name'].lower() == name.lower() for g in get_all_goals()):
        return jsonify({'error': 'Goal already exists'}), 400
    
    add_goal(name, status, deadline, points)
    return jsonify({'success': True})

@app.route('/api/goals/update', methods=['POST'])
def api_update_goal():
    data = request.json
    old_name = data.get('old_name')
    new_name = data.get('new_name', '').strip()
    new_status = data.get('new_status')
    new_deadline = data.get('new_deadline')
    new_points = int(data.get('new_points', 0))
    
    if not new_name:
        return jsonify({'error': 'Name required'}), 400
    
    if update_goal(old_name, new_name, new_status, new_deadline, new_points):
        return jsonify({'success': True})
    else:
        return jsonify({'error': 'Goal name already exists'}), 400

@app.route('/api/goals/delete', methods=['POST'])
def api_delete_goal():
    data = request.json
    name = data.get('name')
    
    delete_goal(name)
    return jsonify({'success': True})

@app.route('/api/progress/<date_str>', methods=['GET'])
def api_progress_for_date(date_str):
    habits = get_all_habits(archived=False)
    completed = get_completed_for_date(date_str)
    
    total_points = 0
    earned_points = 0
    completed_habits = []
    pending_habits = []
    
    for habit in habits:
        points = int(habit.get('points', 0))
        total_points += points
        
        habit_data = {
            'name': habit['name'],
            'points': points
        }
        
        if habit['name'] in completed:
            earned_points += points
            completed_habits.append(habit_data)
        else:
            pending_habits.append(habit_data)
    
    weekly_earned = 0
    weekly_possible = 0
    
    target_date = datetime.strptime(date_str, '%Y-%m-%d')
    for i in range(7):
        day = target_date - timedelta(days=i)
        day_str = day.strftime('%Y-%m-%d')
        snapshot = get_progress_snapshot(day_str)
        
        if snapshot:
            weekly_earned += int(snapshot.get('earned_points', 0))
            weekly_possible += int(snapshot.get('possible_points', 0))
    
    return jsonify({
        'date': date_str,
        'earned_points': earned_points,
        'total_points': total_points,
        'percentage': int((earned_points / total_points * 100) if total_points > 0 else 0),
        'completed_habits': completed_habits,
        'pending_habits': pending_habits,
        'weekly_earned': weekly_earned,
        'weekly_possible': weekly_possible,
        'weekly_percentage': int((weekly_earned / weekly_possible * 100) if weekly_possible > 0 else 0)
    })

@app.route('/api/progress/toggle', methods=['POST'])
def api_toggle_progress():
    data = request.json
    habit_name = data.get('name')
    is_completed = data.get('completed', False)
    date_str = data.get('date')
    
    toggle_completion(habit_name, is_completed, date_str)
    
    habits = get_all_habits(archived=False)
    completed = get_completed_for_date(date_str)
    
    earned = sum(int(h.get('points', 0)) for h in habits if h['name'] in completed)
    possible = sum(int(h.get('points', 0)) for h in habits)
    
    save_progress_snapshot(date_str, earned, possible)
    
    return jsonify({'success': True})

if __name__ == '__main__':
    init_files()
    app.run(host='0.0.0.0', port=5000, debug=True)
