# Use exam-sim from Claude (MCP)

exam-sim serves your own synced exams over MCP at `/mcp`. Claude Code or Claude Desktop, on your own
subscription, then does the quizzing and grading. The server holds no LLM key.

## Connect

1. Sign in to the web app, open Settings → **MCP access**, create a token, and copy it. It is shown only once.
2. Claude Code:

   ```sh
   claude mcp add --transport http exam-sim http://localhost:5173/mcp --header "Authorization: Bearer es_…"
   ```

   `:5173` goes through the Vite dev proxy. `http://localhost:8000/mcp` reaches the backend directly.
3. Claude Desktop, in `claude_desktop_config.json` (via `mcp-remote`, because Desktop's own remote connectors need OAuth):

   ```json
   {
     "mcpServers": {
       "exam-sim": {
         "command": "npx",
         "args": ["mcp-remote", "http://localhost:8000/mcp", "--header", "Authorization: Bearer es_…"]
       }
     }
   }
   ```

Revoke a token in the same Settings section; it stops working on the next call.

## Tools

| Tool | What it does |
|---|---|
| `list_subjects` | your subjects with exam count, handed-in attempts and score share |
| `progress(subject?)` | weakest tasks first, the last 5 attempts, exams never attempted |
| `find_tasks(subject, query?, filter?)` | `unattempted`, `scored_below:<0..1>`, `has_solution`; `query` matches by meaning (local embeddings, closest first) and by text for subtasks the worker has not indexed yet |
| `get_task(ref, include_solution?)` | text, MC options, points and the page crops as images; the solution only when asked |
| `my_history(ref)` | your earlier answers, points and feedback for one subtask |
| `record_practice(results)` | saves graded answers for one task as a handed-in attempt; it syncs to every device |
| `set_points(ref, points)` | fixes a subtask's max points |

A subtask `ref` is `<exam id>/<subtask key>`, e.g. `3f2c…/A2b`.

## Example session

> Quiz me on GRNVS, focus on what I'm bad at.

Claude first asks whether you want hints this session. It then calls `progress("GRNVS")`,
`find_tasks("GRNVS", filter="scored_below:0.5")` and `get_task(ref)`, and asks you the question. With hints on, "I don't know"
gets one hint first; without, Claude shows and explains the solution, and saves it as 0 points. Once you answer, it calls `get_task(ref, include_solution=true)`, grades against the solution (checking
`my_history` for repeated mistakes), and saves the result with `record_practice`. The attempt then shows in Results and
Statistics on every signed-in device.

## Limits

- Bearer tokens instead of MCP OAuth 2.1, so there is no one-click claude.ai connector yet.
- A practice attempt covers a whole task: subtasks of that task you didn't answer count as 0 in Statistics.
- Server-side progress ignores subtasks whose max points come only from the app's MC point split.
