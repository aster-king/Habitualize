from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from datetime import datetime, timedelta
import csv
import os
from functools import wraps

app = Flask(__name__)
app.secret_key = 'habitualize-secret-key-change-this-in-production'

# CSV Files
HABITS_FILE = 'habits.csv'
COMPLETED_FILE = 'completed.csv'
PROGRESS_LOG_FILE = 'progress_log.csv'
GOALS_FILE = 'goals.csv'

# Initialize CSV files
def init_files():
    if not os.path.exists(HABITS_FILE):
        with open(HABITS_FILE, 'w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow(['name', 'points', 'archived', 'creation_date'])
    
    if not os.path.exists(COMPLETED_FILE):
        with open(COMPLETED_FILE, 'w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow(['date', 'name'])
    
    if not os.path.exists(PROGRESS_LOG_FILE):
        with open(PROGRESS_LOG_FILE, 'w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow(['date', 'earned_points', 'possible_points'])
    
    if not os.path.exists(GOALS_FILE):
        with open(GOALS_FILE, 'w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow(['name', 'status', 'deadline', 'points'])

# Data Access Functions
def get_all_habits(archived=None):
    if not os.path.exists(HABITS_FILE):
        return []
    
    with open(HABITS_FILE, 'r', newline='', encoding='utf-8') as f:
        habits = list(csv.DictReader(f))
    
    if archived is None:
        return habits
    
    return [h for h in habits if (h.get('archived', 'False') == 'True') == archived]

def get_all_goals():
    if not os.path.exists(GOALS_FILE):
        return []
    
    with open(GOALS_FILE, 'r', newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))

def get_completed_for_date(date_str):
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

def update_habit(old_name, new_name, new_points):
    habits = get_all_habits()
    
    # Check for duplicate names
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

def add_goal(name, status, deadline, points):
    with open(GOALS_FILE, 'a', newline='', encoding='utf-8') as f:
        csv.writer(f).writerow([name, status, deadline, points])

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
    
    return True

def delete_goal(name):
    goals = [g for g in get_all_goals() if g['name'] != name]
    
    with open(GOALS_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['name', 'status', 'deadline', 'points'])
        writer.writeheader()
        writer.writerows(goals)

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

def get_progress_snapshot(date_str):
    if not os.path.exists(PROGRESS_LOG_FILE):
        return None
    
    with open(PROGRESS_LOG_FILE, 'r', newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if row.get('date') == date_str:
                return row
    return None

# Routes
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
    
    # Save today's progress
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
    
    # Check for duplicates
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
    # Get habits that existed on that date
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
    
    # Get weekly summary
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
    
    # Recalculate and save progress for that date
    habits = get_all_habits(archived=False)
    completed = get_completed_for_date(date_str)
    
    earned = sum(int(h.get('points', 0)) for h in habits if h['name'] in completed)
    possible = sum(int(h.get('points', 0)) for h in habits)
    
    save_progress_snapshot(date_str, earned, possible)
    
    return jsonify({'success': True})

if __name__ == '__main__':
    init_files()
    app.run(host='0.0.0.0', port=5000, debug=True)
