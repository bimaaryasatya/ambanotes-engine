import os
import sys
import datetime
from bson import ObjectId

# Add parent directory to path so we can import from common
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Blueprint, request, jsonify
from common.logger import log_event
from common.jwt_utils import token_required
from common.db import reminders_col

reminder_bp = Blueprint('reminder', __name__)

@reminder_bp.route('/', methods=['POST'])
@token_required
def create_reminder(current_user):
    """
    Create a new reminder/task
    ---
    tags:
      - Reminder
    consumes:
      - application/json
    produces:
      - application/json
    security:
      - BearerAuth: []
    parameters:
      - name: Authorization
        in: header
        type: string
        required: true
        description: "Format: Bearer <token>"
        default: "Bearer "
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - task
            - date
          properties:
            task:
              type: string
              example: "Rapat Koordinasi"
            date:
              type: string
              example: "2026-05-20"
            time:
              type: string
              example: "10:00"
            location:
              type: string
              example: "Aula Utama"
            doc_id:
              type: string
              description: ID dokumen referensi (opsional)
    responses:
      201:
        description: Reminder created successfully
    """
    user_id = current_user.get("user_id")
    org_id = current_user.get("org_id")
    
    data = request.get_json(force=True, silent=True) or {}
    task = data.get('task')
    date = data.get('date')
    
    if not task or not date:
        return jsonify({"error": "Task and Date are required"}), 400

    reminder = {
        "org_id": org_id,
        "created_by": user_id,
        "task": task,
        "date": date,
        "time": data.get('time', ''),
        "location": data.get('location', ''),
        "doc_id": data.get('doc_id', ''),
        "is_completed": False,
        "created_at": datetime.datetime.utcnow()
    }
    
    result = reminders_col.insert_one(reminder)
    
    log_event("reminder_service", f"Reminder created: {task}", 
              user_id=user_id, org_id=org_id, action="REMINDER_CREATE_SUCCESS")
    
    reminder['_id'] = str(result.inserted_id)
    reminder['created_at'] = reminder['created_at'].isoformat()
    
    return jsonify(reminder), 201


@reminder_bp.route('/', methods=['GET'])
@token_required
def list_reminders(current_user):
    """
    List all reminders for the organization
    ---
    tags:
      - Reminder
    consumes:
      - application/json
    produces:
      - application/json
    security:
      - BearerAuth: []
    parameters:
      - name: Authorization
        in: header
        type: string
        required: true
        description: "Format: Bearer <token>"
        default: "Bearer "
    responses:
      200:
        description: List of reminders
    """
    org_id = current_user.get("org_id")
    
    reminders = list(reminders_col.find({"org_id": org_id}).sort("date", 1))
    
    for r in reminders:
        r['_id'] = str(r['_id'])
        r['created_at'] = r['created_at'].isoformat()
        
    return jsonify(reminders), 200


@reminder_bp.route('/<reminder_id>', methods=['DELETE'])
@token_required
def delete_reminder(current_user, reminder_id):
    """
    Delete a reminder
    ---
    tags:
      - Reminder
    consumes:
      - application/json
    produces:
      - application/json
    security:
      - BearerAuth: []
    parameters:
      - name: Authorization
        in: header
        type: string
        required: true
        description: "Format: Bearer <token>"
        default: "Bearer "
      - name: reminder_id
        in: path
        required: true
    responses:
      200:
        description: Reminder deleted successfully
    """
    org_id = current_user.get("org_id")
    
    try:
        obj_id = ObjectId(reminder_id)
    except Exception:
        return jsonify({"error": "Invalid ID format"}), 400
        
    result = reminders_col.delete_one({"_id": obj_id, "org_id": org_id})
    
    if result.deleted_count:
        log_event("reminder_service", f"Reminder deleted: {reminder_id}", 
                  user_id=current_user.get("user_id"), org_id=org_id, action="REMINDER_DELETE_SUCCESS")
        return jsonify({"message": "Reminder deleted successfully"}), 200
        
    return jsonify({"error": "Reminder not found or unauthorized"}), 404


@reminder_bp.route('/health', methods=['GET'])
def health_check():
    log_event("reminder_service", "Health check requested", action="HEALTH_CHECK")
    return jsonify({"status": "healthy", "service": "reminder_service"}), 200
