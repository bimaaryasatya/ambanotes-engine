import os
import sys
from flask import Blueprint, render_template, redirect, request, url_for, jsonify
from common.db import logs_col

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.jwt_utils import verify_token
from common.config import Config

dashboard_bp = Blueprint('dashboard_web', __name__, template_folder='templates')

def get_current_user_from_cookie():
    token = request.cookies.get("token")
    if not token:
        return None
    try:
        return verify_token(token)
    except Exception:
        return None

@dashboard_bp.route('/login', methods=['GET'])
def login_page():
    user = get_current_user_from_cookie()
    if user:
        if user.get('role') == 'owner':
            return redirect(url_for('dashboard_web.owner_dashboard'))
        elif user.get('role') == 'developer':
            return redirect(url_for('dashboard_web.dev_console'))
    return render_template('login.html')

@dashboard_bp.route('/dashboard', methods=['GET'])
def owner_dashboard():
    user = get_current_user_from_cookie()
    if not user:
        return redirect(url_for('dashboard_web.login_page'))
    if user.get('role') != 'owner':
        return "Access forbidden: Owner role required", 403
    return render_template('owner_dashboard.html', user=user)

@dashboard_bp.route('/console', methods=['GET'])
def dev_console():
    user = get_current_user_from_cookie()
    if not user:
        return redirect(url_for('dashboard_web.login_page'))
    if user.get('role') != 'developer':
        return "Access forbidden: Developer role required", 403
    return render_template('dev_console.html', user=user)

@dashboard_bp.route('/logout', methods=['GET'])
def logout():
    response = redirect(url_for('dashboard_web.login_page'))
    # Clear the token cookie
    response.set_cookie('token', '', expires=0, path='/')
    return response

@dashboard_bp.route('/dev/api/logs', methods=['GET'])
def get_system_logs():
    user = get_current_user_from_cookie()
    if not user or user.get('role') != 'developer':
        return jsonify({"error": "Unauthorized"}), 401
    try:
        limit = request.args.get('limit', default=100, type=int)
        logs = list(logs_col.find().sort("timestamp", -1).limit(limit))
        result = []
        for l in logs:
            result.append({
                "id": str(l.get("_id")),
                "service": l.get("service"),
                "message": l.get("message"),
                "action": l.get("action"),
                "severity": l.get("severity", "info"),
                "timestamp": l.get("timestamp").isoformat() if l.get("timestamp") else None
            })
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
