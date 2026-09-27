from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Annotated

from auth import get_current_user
from database import get_db
from models import Todo, User
from schemas import NewTask, UpdateTask, ChatRequest
from ai_assistant import generate_task, generate_ai_response


task = APIRouter(prefix="/tasks", tags=["tasks"])


user_dependency = Annotated[User, Depends(get_current_user)]
db_dependency = Annotated[Session, Depends(get_db)]


# Note for production: If you run this app with multiple workers (e.g., Uvicorn workers > 1), 
# this memory won't be shared. You should eventually move this to a Database table or Redis.
pending_suggestions = {}


@task.post("/create", status_code=status.HTTP_201_CREATED)
def create_task(
    task: NewTask,
    db: db_dependency,
    user: user_dependency
):
    task_schema = generate_task(task.description)

    new_task = Todo(
        title=task_schema["title"],
        description=task_schema["description"],
        priority=task_schema["priority"],
        due=task_schema["due"],
        user_id=user.id
    )

    db.add(new_task)
    db.commit()
    db.refresh(new_task)

    return {
        "message": "Task Created Successfully",
        "task": new_task
    }


@task.patch("/update/{task_id}")
def update(
    task_id: int,
    task: UpdateTask,
    user: user_dependency,
    db: db_dependency
):
    existing_task = (
        db.query(Todo)
        .filter(
            Todo.id == task_id,
            Todo.user_id == user.id
        )
        .first()
    )

    if existing_task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task Not Found"
        )

    updated_task_data = generate_task(task.description)

    existing_task.title = updated_task_data["title"]
    existing_task.description = updated_task_data["description"]
    existing_task.priority = updated_task_data["priority"]
    existing_task.due = updated_task_data["due"]

    db.commit()
    db.refresh(existing_task)

    return {
        "message": "Task Updated Successfully",
        "updated_task": existing_task
    }


@task.patch("/update-status/{task_id}")
def update_task_status(
    task_id: int,
    is_done: bool,
    user: user_dependency,
    db: db_dependency
):
    existing_task = (
        db.query(Todo)
        .filter(
            Todo.id == task_id,
            Todo.user_id == user.id
        )
        .first()
    )

    if existing_task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task Not Found"
        )

    existing_task.is_done = is_done

    db.commit()
    db.refresh(existing_task)

    return {
        "message": "Task status updated",
        "task": existing_task
    }


@task.get("/view-tasks")
def view_tasks(
    user: user_dependency,
    db: db_dependency
):
    tasks = (
        db.query(Todo)
        .filter(Todo.user_id == user.id)
        .all()
    )

    return tasks


@task.delete("/delete-task/{task_id}")
def delete(
    task_id: int,
    user: user_dependency,
    db: db_dependency
):
    existing_task = (
        db.query(Todo)
        .filter(
            Todo.id == task_id,
            Todo.user_id == user.id
        )
        .first()
    )

    if existing_task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task Not Found"
        )

    db.delete(existing_task)
    db.commit()

    return {
        "message": "Task Deleted Successfully"
    }


@task.post("/chat")
def ai_chat_bot(
    request: ChatRequest,
    user: user_dependency,
    db: db_dependency
):
    user_id = user.id
    message = request.message

    if message.strip().lower() in ["yes", "y", "ok", "okay"]:
        pending_tasks = pending_suggestions.get(user_id)

        if pending_tasks:
            for suggested_task in pending_tasks:
                new_task = Todo(
                    title=suggested_task.title,
                    description=suggested_task.description,
                    priority=suggested_task.priority,
                    due=suggested_task.due,
                    user_id=user_id
                )
                db.add(new_task)

            db.commit()
            del pending_suggestions[user_id]

            return {
                "message": "I've created the suggested tasks.",
                "conversation_complete": True
            }

    tasks = (
        db.query(Todo)
        .filter(Todo.user_id == user_id)
        .all()
    )

    task_data = [
        {
            "id": todo.id,
            "title": todo.title,
            "description": todo.description,
            "priority": todo.priority,
            "due": todo.due,
            "is_done": todo.is_done
        }
        for todo in tasks
    ]

    ai_response = generate_ai_response(
        message,
        task_data
    )

    if ai_response.action == "chat":
        return {
            "message": ai_response.message
        }

    elif ai_response.action == "summarize":
        return {
            "message": ai_response.message
        }

    elif ai_response.action == "create_task":
        created_tasks = []

        for ai_task in ai_response.tasks:
            new_task = Todo(
                title=ai_task.title,
                description=ai_task.description,
                priority=ai_task.priority,
                due=ai_task.due,
                user_id=user_id
            )

            db.add(new_task)
            created_tasks.append(new_task)

        db.commit()

        for new_task in created_tasks:
            db.refresh(new_task)

        return {
            "message": "Task created successfully.",
            "tasks": created_tasks,
            "conversation_complete": True
        }

    elif ai_response.action == "update_task":
        existing_task = (
            db.query(Todo)
            .filter(
                Todo.id == ai_response.task_id,
                Todo.user_id == user_id
            )
            .first()
        )

        if existing_task is None:
            return {
                "message": "I couldn't find the task you're trying to update. Please check the task details.",
                "conversation_complete": True
            }

        if not ai_response.tasks:
            return {
                "message": "I didn't get the updated information for the task. Could you please clarify?",
                "conversation_complete": True
            }

        updated_task = ai_response.tasks[0]

        existing_task.title = updated_task.title
        existing_task.description = updated_task.description
        existing_task.priority = updated_task.priority
        existing_task.due = updated_task.due

        db.commit()
        db.refresh(existing_task)

        return {
            "message": "Task Updated Successfully",
            "task": existing_task,
            "conversation_complete": True
        }

    elif ai_response.action == "delete_task":
        existing_task = (
            db.query(Todo)
            .filter(
                Todo.id == ai_response.task_id,
                Todo.user_id == user_id
            )
            .first()
        )

        if existing_task is None:
            return {
                "message": "I couldn't find that task to delete. It might have already been removed.",
                "conversation_complete": True
            }

        db.delete(existing_task)
        db.commit()

        return {
            "message": "Task Deleted Successfully",
            "conversation_complete": True
        }

    elif ai_response.action == "complete_task":
        existing_task = (
            db.query(Todo)
            .filter(
                Todo.id == ai_response.task_id,
                Todo.user_id == user_id
            )
            .first()
        )

        if existing_task is None:
            return {
                "message": "I couldn't find that task to complete. Are you sure you referenced the right one?",
                "conversation_complete": True
            }

        existing_task.is_done = True

        db.commit()
        db.refresh(existing_task)

        return {
            "message": "Task completed successfully.",
            "task": existing_task,
            "conversation_complete": True
        }

    elif ai_response.action == "suggest_tasks":
        pending_suggestions[user_id] = ai_response.tasks

        return {
            "message": ai_response.message,
            "suggested_tasks": ai_response.tasks,
            "requires_confirmation": True
        }

    elif ai_response.action == "out_of_scope":
        return {
            "message": (
                "I can only help with your tasks. "
                "I can create, update, complete, delete, "
                "summarize, or suggest tasks."
            )
        }

    else:
        return {
            "message": "I'm not sure how to handle that request right now.",
            "conversation_complete": True
        }