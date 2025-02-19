import os
import json
import datetime
from typing import Dict, List, Tuple
from notion_client import Client
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Constants
NOTION_TOKEN = os.environ["NOTION_TOKEN"]
MAIN_DB_ID = os.environ["MAIN_DB_ID"]
LOG_DB_ID = os.environ["LOG_DB_ID"]
USER_1_ID = os.environ["USER_1_ID"]
USER_2_ID = os.environ["USER_2_ID"]

WEEKDAY_TO_STR = {
    0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"
}

COMPLETE_EMOJI = "✅"
IN_PROGRESS_EMOJI = "⭕️"

# Add list of task properties
TASK_PROPERTIES = [
    "Work Tasks",
    "Personal Tasks",
    "Wedding",
    "School Tasks",
    "Tuscany",
    "Albus Tasks"
]

def initialize_task_dict() -> Dict:
    """Initialize nested dictionary structure for tasks with person layer."""
    task_dict = {}
    for person_id in [USER_1_ID, USER_2_ID]:
        task_dict[person_id] = {}
        for prop in TASK_PROPERTIES:  # renamed loop variable to avoid shadowing built-ins
            task_dict[person_id][prop] = {
                "DAILY CONSUMPTION": [],
                "MUST": [],
                "TIME PERMITTING": []
            }
    return task_dict

def get_dates() -> Tuple[datetime.date, datetime.date]:
    """Get today's and yesterday's dates."""
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)
    return today, yesterday

def get_plain_text(rich_text_blocks: List[dict]) -> str:
    """Extract plain text from rich text blocks."""
    return ''.join(block.get('plain_text', '') for block in rich_text_blocks)

def find_category_boundaries(rich_text_blocks: List[dict]) -> List[Tuple[str, int, int]]:
    """Find the start and end indices of each category in the rich text blocks."""
    categories = []
    current_start = None
    current_category = None

    for i, block in enumerate(rich_text_blocks):
        text = block.get('plain_text', '').strip()

        if text in ["DAILY CONSUMPTION", "MUST", "TIME PERMITTING"]:
            if current_category:
                categories.append((current_category, current_start, i - 1))
            current_category = text
            current_start = i

    if current_category and current_start is not None:
        categories.append((current_category, current_start, len(rich_text_blocks) - 1))

    return categories

def extract_tasks(rich_text_blocks: List[dict], start_idx: int, end_idx: int) -> List[List[dict]]:
    """Extract tasks from a section of rich text blocks.
    Each task starts with '-' at the beginning of a line."""
    tasks = []
    current_task = []

    for block in rich_text_blocks[start_idx:end_idx + 1]:
        text = block.get('plain_text', '')

        # Skip category headers
        if text.strip() in ["DAILY CONSUMPTION", "MUST", "TIME PERMITTING"]:
            continue

        # Split on newlines to find task starts
        lines = text.split('\n')
        for i, line in enumerate(lines):
            if not line.strip():
                continue

            if line.lstrip().startswith('-'):  # Line starts with dash (ignoring leading spaces)
                if current_task:
                    tasks.append(current_task)
                    current_task = []

                new_block = {
                    'type': block.get('type', 'text'),
                    'text': {
                        'content': line,
                    },
                    'plain_text': line
                }

                if block.get('text', {}).get('link'):
                    new_block['text']['link'] = block['text']['link']

                if 'annotations' in block:
                    new_block['annotations'] = block['annotations']

                if 'href' in block:
                    new_block['href'] = block['href']

                current_task = [new_block]
            elif current_task:
                new_block = {
                    'type': block.get('type', 'text'),
                    'text': {
                        'content': line,
                    },
                    'plain_text': line
                }

                if block.get('text', {}).get('link'):
                    new_block['text']['link'] = block['text']['link']

                if 'annotations' in block:
                    new_block['annotations'] = block['annotations']

                if 'href' in block:
                    new_block['href'] = block['href']

                current_task.append(new_block)

    if current_task:
        tasks.append(current_task)

    return tasks

def categorize_tasks(rich_text_blocks: List[dict]) -> Tuple[List[List[dict]], List[List[dict]], List[List[dict]]]:
    """Categorize tasks from rich text blocks into DC, MUST, and TIME PERMITTING."""
    dc_tasks = []
    must_tasks = []
    time_permitting_tasks = []

    categories = find_category_boundaries(rich_text_blocks)

    for category, start, end in categories:
        tasks = extract_tasks(rich_text_blocks, start, end)

        if category == "DAILY CONSUMPTION":
            dc_tasks.extend(tasks)
        elif category == "MUST":
            must_tasks.extend(tasks)
        elif category == "TIME PERMITTING":
            time_permitting_tasks.extend(tasks)

    return dc_tasks, must_tasks, time_permitting_tasks

def create_rich_text_section(category: str, tasks: List[List[dict]], is_last_section: bool = False) -> List[dict]:
    """Create a rich text section for a category with its tasks."""
    if not tasks:
        return []

    rich_text = [
        {
            "type": "text",
            "text": {"content": f"{category}\n"},
            "annotations": {"underline": True}
        }
    ]

    for i, task_blocks in enumerate(tasks):
        rich_text.extend(task_blocks)
        if not (is_last_section and i == len(tasks) - 1):
            rich_text.append({
                "type": "text",
                "text": {"content": "\n"}
            })

    if not is_last_section:
        rich_text.append({
            "type": "text",
            "text": {"content": "\n"}
        })

    return rich_text

def create_todays_page(client, person_id: str, today: datetime.date) -> dict:
    """Create a new page for today if it doesn't exist."""
    day_of_week = today.weekday()
    day_str = WEEKDAY_TO_STR[day_of_week]

    new_page = client.pages.create(
        parent={"database_id": MAIN_DB_ID},
        properties={
            "Date": {
                "date": {
                    "start": today.isoformat()
                }
            },
            "Day": {
                "select": {
                    "name": day_str
                }
            },
            "Person": {
                "people": [
                    {
                        "id": person_id
                    }
                ]
            },
            **{prop: {"rich_text": []} for prop in TASK_PROPERTIES}
        }
    )
    return new_page

def validate_rich_text_content(rich_text_blocks: List[dict]) -> bool:
    """Validate that rich text content meets Notion's size limits."""
    total_length = 0
    for block in rich_text_blocks:
        content = block.get('text', {}).get('content', '')
        if len(content) > 2000:
            print(f"Warning: Text content exceeds 2000 character limit: {len(content)} characters")
            return False

        url = block.get('text', {}).get('link', {}).get('url', '')
        if url and len(url) > 2000:
            print(f"Warning: URL exceeds 2000 character limit: {len(url)} characters")
            return False

        total_length += len(content)

    if total_length > 2000:
        print(f"Warning: Total content exceeds 2000 character limit: {total_length} characters")
        return False

    return True

def update_page_property_safely(client, page_id: str, property_name: str, rich_text_content: List[dict]):
    """Update a page property with size limit handling.
    
    Note: The empty-content check was removed so that properties can be cleared.
    """
    print(f"\nUpdating property: {property_name}")
    total_chars = sum(len(block.get('text', {}).get('content', '')) for block in rich_text_content)
    print(f"Initial content length: {total_chars} characters")

    if validate_rich_text_content(rich_text_content):
        print("Content within limits, updating normally")
        client.pages.update(
            page_id=page_id,
            properties={
                property_name: {
                    "rich_text": rich_text_content
                }
            }
        )
    else:
        chunks = chunk_rich_text_content(rich_text_content, property_name)
        print(f"Split content into {len(chunks)} chunks")
        current_page = client.pages.retrieve(page_id)
        accumulated_content = []

        for i, chunk in enumerate(chunks):
            chunk_length = sum(len(block.get('text', {}).get('content', '')) for block in chunk)
            print(f"\nProcessing chunk {i+1}/{len(chunks)}")
            print(f"Chunk length: {chunk_length} characters")
            accumulated_content.extend(chunk)
            acc_length = sum(len(block.get('text', {}).get('content', '')) for block in accumulated_content)
            print(f"Updating with accumulated content length: {acc_length} characters")
            client.pages.update(
                page_id=page_id,
                properties={
                    property_name: {
                        "rich_text": accumulated_content
                    }
                }
            )

def chunk_rich_text_content(rich_text_blocks: List[dict], property_name: str) -> List[List[dict]]:
    """Split rich text content into chunks under 2000 characters while preserving task sections."""
    categories = {
        "DAILY CONSUMPTION": [],
        "MUST": [],
        "TIME PERMITTING": []
    }
    current_category = None

    print("\nGrouping tasks by category:")
    for block in rich_text_blocks:
        content = block.get('text', {}).get('content', '').strip()

        if content in categories.keys():
            current_category = content
            print(f"\nProcessing category: {content}")
            continue

        if current_category:
            categories[current_category].append(block)
            print(f"Added task to {current_category}")

    chunks = []
    current_chunk = []
    current_length = 0

    print("\nCreating chunks:")
    for category in ["DAILY CONSUMPTION", "MUST", "TIME PERMITTING"]:
        tasks = categories[category]
        if not tasks:
            print(f"No tasks in {category}")
            continue

        print(f"\nProcessing {category} with {len(tasks)} tasks")
        header_block = {
            "type": "text",
            "text": {"content": f"{category}\n"},
            "annotations": {"underline": True}
        }
        header_length = len(category) + 1

        if current_length + header_length > 1900:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = []
            current_length = 0

        current_chunk.append(header_block)
        current_length += header_length
        print(f"Added category header, current length: {current_length}")

        task_buffer = []
        task_buffer_length = 0
        is_first_chunk_of_category = True

        for block in tasks:
            block_length = len(block.get('text', {}).get('content', ''))

            if current_length + task_buffer_length + block_length > 1900:
                print(f"Task would exceed limit ({current_length + task_buffer_length + block_length} chars)")
                if task_buffer:
                    print("Adding buffered tasks to chunk")
                    current_chunk.extend(task_buffer)
                    chunks.append(current_chunk)
                print("Starting new chunk")
                current_chunk = []
                current_length = 0
                task_buffer = [block]
                task_buffer_length = block_length
                is_first_chunk_of_category = False
            else:
                task_buffer.append(block)
                task_buffer_length += block_length
                print("Added task to buffer")

        if task_buffer:
            if current_length + task_buffer_length <= 1900:
                print("Adding remaining buffer to current chunk")
                current_chunk.extend(task_buffer)
                current_length += task_buffer_length
            else:
                print("Starting new chunk for remaining buffer")
                chunks.append(current_chunk)
                current_chunk = task_buffer

    if current_chunk:
        print("Adding final chunk")
        chunks.append(current_chunk)

    print(f"\nCreated {len(chunks)} chunks")
    for i, chunk in enumerate(chunks):
        chunk_length = sum(len(block.get('text', {}).get('content', '')) for block in chunk)
        print(f"Chunk {i+1} length: {chunk_length} characters")

    return chunks

def get_existing_tasks(page_properties: dict, property_name: str) -> dict:
    """Extract existing tasks from a page property and categorize them."""
    existing_tasks = {
        "DAILY CONSUMPTION": [],
        "MUST": [],
        "TIME PERMITTING": []
    }

    if property_name in page_properties:
        property_content = page_properties[property_name]['rich_text']
        dc_tasks, must_tasks, time_permitting_tasks = categorize_tasks(property_content)

        existing_tasks["DAILY CONSUMPTION"] = dc_tasks
        existing_tasks["MUST"] = must_tasks
        existing_tasks["TIME PERMITTING"] = time_permitting_tasks

    return existing_tasks

def merge_tasks(existing_tasks: List[List[dict]], new_tasks: List[List[dict]]) -> List[List[dict]]:
    """Merge new tasks with existing tasks, avoiding duplicates."""
    existing_task_texts = set(get_plain_text(task) for task in existing_tasks)
    merged_tasks = existing_tasks.copy()

    for new_task in new_tasks:
        new_task_text = get_plain_text(new_task)
        if new_task_text not in existing_task_texts:
            merged_tasks.append(new_task)
            existing_task_texts.add(new_task_text)

    return merged_tasks

def main():
    """Main execution function."""
    client = Client(auth=NOTION_TOKEN)
    log_id = None

    try:
        today, yesterday = get_dates()

        tasks_that_should_remain_behind = initialize_task_dict()
        tasks_that_should_go_forward = initialize_task_dict()
        todays_preexisting_tasks = initialize_task_dict()

        for person_id in [USER_1_ID, USER_2_ID]:
            print(f"\nProcessing person: {person_id}")

            yesterday_results = client.databases.query(
                database_id=MAIN_DB_ID,
                filter={
                    "and": [
                        {
                            "property": "Date",
                            "date": {
                                "equals": yesterday.isoformat()
                            }
                        },
                        {
                            "property": "Person",
                            "people": {
                                "contains": person_id
                            }
                        }
                    ]
                }
            )

            today_results = client.databases.query(
                database_id=MAIN_DB_ID,
                filter={
                    "and": [
                        {
                            "property": "Date",
                            "date": {
                                "equals": today.isoformat()
                            }
                        },
                        {
                            "property": "Person",
                            "people": {
                                "contains": person_id
                            }
                        }
                    ]
                }
            )

            if not today_results['results']:
                today_page = create_todays_page(client, person_id, today)
                today_results = {'results': [today_page]}

            if yesterday_results['results']:
                yesterday_page = yesterday_results['results'][0]
                for property_name in TASK_PROPERTIES:
                    if property_name in yesterday_page['properties']:
                        property_content = yesterday_page['properties'][property_name]['rich_text']

                        dc_tasks, must_tasks, time_permitting_tasks = categorize_tasks(property_content)

                        # Process DAILY CONSUMPTION tasks: all tasks remain behind, and completed tasks get cleaned and carried forward
                        for task_blocks in dc_tasks:
                            task_text = get_plain_text(task_blocks)
                            tasks_that_should_remain_behind[person_id][property_name]["DAILY CONSUMPTION"].append(task_blocks)

                            if task_text.strip().endswith(COMPLETE_EMOJI):
                                clean_blocks = task_blocks[:-1] + [{
                                    **task_blocks[-1],
                                    'text': {
                                        **task_blocks[-1]['text'],
                                        'content': task_blocks[-1]['text']['content'].rstrip(COMPLETE_EMOJI).rstrip()
                                    },
                                    'plain_text': task_blocks[-1]['plain_text'].rstrip(COMPLETE_EMOJI).rstrip()
                                }]
                                tasks_that_should_go_forward[person_id][property_name]["DAILY CONSUMPTION"].append(clean_blocks)
                            else:
                                tasks_that_should_go_forward[person_id][property_name]["DAILY CONSUMPTION"].append(task_blocks)

                        # Process MUST tasks: only completed tasks remain behind, incomplete tasks go forward
                        for task_blocks in must_tasks:
                            task_text = get_plain_text(task_blocks)
                            if task_text.strip().endswith(COMPLETE_EMOJI):
                                tasks_that_should_remain_behind[person_id][property_name]["MUST"].append(task_blocks)
                            else:
                                tasks_that_should_go_forward[person_id][property_name]["MUST"].append(task_blocks)

                        # Process TIME PERMITTING tasks: only completed tasks remain behind, incomplete tasks go forward
                        for task_blocks in time_permitting_tasks:
                            task_text = get_plain_text(task_blocks)
                            if task_text.strip().endswith(COMPLETE_EMOJI):
                                tasks_that_should_remain_behind[person_id][property_name]["TIME PERMITTING"].append(task_blocks)
                            else:
                                tasks_that_should_go_forward[person_id][property_name]["TIME PERMITTING"].append(task_blocks)

            # Always update yesterday's page so that if there are no completed tasks the property gets cleared
            if yesterday_results['results']:
                yesterday_page = yesterday_results['results'][0]

                print("\nUpdating yesterday's page with remaining tasks")
                for property_name in TASK_PROPERTIES:
                    remaining_tasks = tasks_that_should_remain_behind[person_id][property_name]
                    rich_text_content = []

                    sections = [
                        ("DAILY CONSUMPTION", remaining_tasks["DAILY CONSUMPTION"]),
                        ("MUST", remaining_tasks["MUST"]),
                        ("TIME PERMITTING", remaining_tasks["TIME PERMITTING"])
                    ]

                    last_section_idx = -1
                    for i, (_, tasks) in enumerate(sections):
                        if tasks:
                            last_section_idx = i

                    for i, (category, tasks) in enumerate(sections):
                        if tasks:
                            is_last = (i == last_section_idx)
                            rich_text_content.extend(
                                create_rich_text_section(
                                    category,
                                    tasks,
                                    is_last_section=is_last
                                )
                            )
                    print(f"  Updating {property_name} with remaining tasks (may be empty)")
                    update_page_property_safely(client, yesterday_page['id'], property_name, rich_text_content)

            if today_results['results']:
                today_page = today_results['results'][0]
                person_properties = []
                print("\nFinding properties to update:")
                for property_name in TASK_PROPERTIES:
                    property_tasks = tasks_that_should_go_forward[person_id][property_name]
                    if any(property_tasks.values()):
                        person_properties.append(property_name)
                        print(f"  {property_name} has tasks")

                print("\nProcessing properties:", person_properties)

                for property_idx, property_name in enumerate(person_properties):
                    print(f"\nProcessing property {property_idx + 1}/{len(person_properties)}: {property_name}")

                    existing_tasks = get_existing_tasks(today_page['properties'], property_name)

                    merged_tasks = {
                        "DAILY CONSUMPTION": merge_tasks(
                            existing_tasks["DAILY CONSUMPTION"],
                            tasks_that_should_go_forward[person_id][property_name]["DAILY CONSUMPTION"]
                        ),
                        "MUST": merge_tasks(
                            existing_tasks["MUST"],
                            tasks_that_should_go_forward[person_id][property_name]["MUST"]
                        ),
                        "TIME PERMITTING": merge_tasks(
                            existing_tasks["TIME PERMITTING"],
                            tasks_that_should_go_forward[person_id][property_name]["TIME PERMITTING"]
                        )
                    }

                    rich_text_content = []
                    sections = [
                        ("DAILY CONSUMPTION", merged_tasks["DAILY CONSUMPTION"]),
                        ("MUST", merged_tasks["MUST"]),
                        ("TIME PERMITTING", merged_tasks["TIME PERMITTING"])
                    ]

                    last_section_idx = -1
                    for i, (_, tasks) in enumerate(sections):
                        if tasks:
                            last_section_idx = i

                    for i, (category, tasks) in enumerate(sections):
                        if tasks:
                            is_last = (i == last_section_idx)
                            rich_text_content.extend(
                                create_rich_text_section(
                                    category,
                                    tasks,
                                    is_last_section=is_last
                                )
                            )
                    if rich_text_content:
                        update_page_property_safely(client, today_page['id'], property_name, rich_text_content)

    except Exception as e:
        print(f"An error occurred: {str(e)}")
        raise

if __name__ == "__main__":
    print("Starting task automation...")
    main()
