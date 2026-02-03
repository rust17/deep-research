@tool
func save_findings()

@tool
func save_progress()

@tool
func save_plan()

@tool
func readfile()

@tool
func web_search()

@tool
func visit_page()

init plan # save_plan

init findings # save_findings
init progress # save_progress

while loop_count < max_loops:
    try:
        plan = get plan # readfile

        result = llm -> research(plan)

        llm -> decide whether web_search()

        llm -> decide whether # save_findings(llm summarize result)

        llm -> decide whether # save_progress(result)

        llm -> decide whether # save_plan(result)
    except:
        log in plan # save_plan

        log in progress # save_progress

    plan = get plan # readfile
    progress = get progress # readfile

    if not llm -> decide whether continue by plan and progress:
        break

llm decide all tasks complete by
