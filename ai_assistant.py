import os
import json
from datetime import datetime
import groq  # Make sure this is imported to catch groq.BadRequestError
from groq import Groq
from dotenv import load_dotenv

from schemas import Task_Response, AIAssistantResponse

load_dotenv()

api_key = os.getenv("GROQ_API_KEY")
model = os.getenv("MODEL_NAME")

if not api_key:
    raise ValueError("GROQ_API_KEY is not configured.")

if not model:
    raise ValueError("MODEL_NAME is not configured.")

groq_client = Groq(api_key=api_key)


def get_system_instruction() -> str:
    current_datetime = datetime.now().strftime("%d-%m-%Y %H:%M")

    return f"""
You are AEGIS, an AI assistant inside a Todo application. Classify every user request into EXACTLY ONE action:

1. `chat` — Normal Todo conversation.
2. `summarize` — Summarize existing tasks, priorities, deadlines, or workload.
3. `create_task` — Explicitly create/add/make task(s).
4. `update_task` — Modify an existing task.
5. `delete_task` — Delete/remove an existing task.
6. `complete_task` — Mark an existing task completed/done.
7. `suggest_tasks` — Brainstorm and recommend NEW tasks or logical next steps based on the user's goals, context, or current workload.
8. `out_of_scope` — Unrelated to Todo/task management.

DATETIME & DATA RULES:
* Current datetime: `{current_datetime}`. Resolve relative dates using this.
* Due dates MUST be `DD-MM-YYYY HH:MM`. If unspecified, use exactly `"No Due Date"`.
* For existing tasks: NEVER invent IDs, dates, or ownership. Use only IDs from the provided task list.
* For new and suggested tasks: You MUST generate a clear, detailed `description` (1-2 sentences) explaining exactly what needs to be done. NEVER leave `description` empty.

TASK MATCHING (For Updates/Deletions/Completions):
* Match references to existing tasks only when sufficiently clear.
* If a requested task is ambiguous or unmatched, ask for clarification in `message`, use the `chat` action, and perform no database operations.

ACTION RULES:
* `create_task`: Put explicitly requested new tasks in `tasks`. 
* `update_task`: Modify only explicitly requested fields. Requires a valid existing `task_id`. Never overwrite unspecified fields.
* `delete_task` / `complete_task`: Requires an explicit request and a valid existing `task_id`.
* `suggest_tasks`: Invent helpful, logical NEW tasks the user should do to achieve their goals. Put these new ideas in `tasks` and explain why you suggested them in `message`.
* `summarize`: Base your summary only on the provided existing task data.
* `chat`: Todo-related conversation requiring no database operations.
* `out_of_scope`: Politely state you handle Todo/task creation, updates, deletion, completion, summaries, and suggestions.

CONFIRMATION RULES:
* `suggest_tasks` = true
* `create_task`, `update_task`, `delete_task`, `complete_task`, `chat`, `summarize`, `out_of_scope` = false

OUTPUT STRICTNESS:
* Return EXACTLY ONE JSON object matching the provided response schema.
* NO Markdown, NO code fences, NO text outside the JSON object.
* CRITICAL: NEVER return plain conversational text. If you are confused or need to ask a clarifying question, put your question INSIDE the "message" string of the JSON object using the "chat" action.
* ALL required schema fields must always be present.
* For `chat`, `summarize`, and `out_of_scope`: `task_id=null`, `requires_confirmation=false`, `tasks=[]`, response in `message`.
* The backend performs all database operations; never claim you personally created, updated, deleted, or completed anything.
* Keep `message` concise, natural, and helpful.
"""


def generate_task(task: str):
    response = groq_client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": """
You are AEGIS (Adaptive Engine for Guidance & Intelligent Scheduling), an AI assistant inside a Todo application. Convert the user's request into exactly one structured Todo task.

Priority:
high: urgent, important, deadline-driven, academic/work obligations, exams, assignments, submissions, applications, or serious consequences.
medium: useful/important but not urgent.
low: optional, recreational, hobby, entertainment, or non-essential.

Rules:
1. You MUST write a clear, detailed `description` (1-2 sentences) explaining exactly what needs to be done. NEVER leave the description empty.
2. If the user's request is very short (e.g., "buy milk"), logically expand the description yourself (e.g., "Purchase milk from the grocery store").
3. Use only information provided by the user for dates and titles; never invent deadlines.
4. If no due date/time is provided, use exactly "No Due Date".
5. Return only the structured response matching the provided schema."""
            },
            {
                "role": "user",
                "content": task,
            },
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "task_response",
                "strict": True,
                "schema": Task_Response.model_json_schema(),
            },
        },
    )

    raw_response = response.choices[0].message.content
    if not raw_response:
        raise ValueError("Groq returned an empty response while generating a task.")

    return Task_Response.model_validate_json(raw_response).model_dump()


def generate_ai_response(user_message: str, tasks: list[dict]) -> AIAssistantResponse:
    task_context = json.dumps(tasks, indent=2, default=str)
    user_prompt = f"""
USER'S EXISTING TASKS:
{task_context}
============================================================
USER REQUEST:
{user_message}
"""
    try:
        response = groq_client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": get_system_instruction(),
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            response_format={
                "type": "json_object"
            },
        )
        
        raw_response = response.choices[0].message.content
        if not raw_response:
            raise ValueError("Groq returned an empty response from AEGIS.")
            
        data = json.loads(raw_response)

    except groq.BadRequestError as e:
        # Catch Groq JSON validation failures (fixes the 500 error crash)
        error_details = e.response.json()
        failed_text = error_details.get("error", {}).get(
            "failed_generation", 
            "I'm a bit confused. Could you rephrase that?"
        )
        data = {
            "action": "chat",
            "message": failed_text,
            "task_id": None,
            "requires_confirmation": False,
            "tasks": []
        }
    except json.JSONDecodeError as exc:
        # Fallback for generic JSON parse failures
        data = {
            "action": "chat",
            "message": "I had some trouble understanding that. Could you try asking again?",
            "task_id": None,
            "requires_confirmation": False,
            "tasks": []
        }
    except Exception as e:
        # Fallback if the API times out or goes down
        data = {
            "action": "chat",
            "message": "Sorry, I'm having a little trouble connecting right now. Please try again.",
            "task_id": None,
            "requires_confirmation": False,
            "tasks": []
        }

    # Clean up minor hallucinations before validating
    if "intent" in data and "action" not in data:
        data["action"] = data.pop("intent")
    
    for task in data.get("tasks", []):
        if "priority" in task:
            task["priority"] = task["priority"].lower()
        if "due_date" in task and "due" not in task:
            task["due"] = task.pop("due_date")
        if "description" not in task:
            task["description"] = task.get("title", "No description provided.")
        if "priority" not in task:
            task["priority"] = "medium"
            
    return AIAssistantResponse.model_validate(data)