# Bot Arena

A desktop application (Python + tkinter) where users write their own bots in Python and watch them compete on a 20×20 grid.

Each bot is a single Python class that receives the current game state every turn and returns one action: move, shoot or place a trap. The goal is to collect crystals scattered across the map and bring them back to the bot's base. A bot can carry at most 3 crystals at a time. Bots can shoot each other in a straight line (walls block the shot). A hit bot drops its crystals and is stunned for a few turns. Bots can also set traps that the opponent cannot see. Maps are randomly generated from a seed and are rotationally symmetric, so neither side has an advantage.

The application offers:
- **Duel mode**: your bot against one of three built-in bots (Easy, Medium, Hard) or against another of your own bots. The built-in bots also serve as documented examples to copy and improve.
- **Solo mode**: a single bot collects all crystals on a random map in as few turns as possible, with a best score kept for each map.
- **Built-in code editor** with syntax highlighting, error reporting with line numbers, and saving bots under a custom name.
- **Match replay**: every match is saved and can be reviewed turn by turn, like analysing a chess game. You can step forward and backward, jump to any turn, and read a log of each bot's decisions together with an optional message explaining *why* it made them.
- **Series**: the same two bots play many matches on different maps in parallel, and the result shows win rates and statistics.

## The project will use

- **concurrency**: every bot runs in its own process (`multiprocessing`) with a per-turn time limit; `asyncio` collects both bots' decisions simultaneously each turn; a background thread keeps the GUI responsive during a match; series of matches run in parallel with `concurrent.futures`
- **interfaces, protocols and ABCs**: a `Bot` protocol that every user bot must satisfy (no inheritance required), an abstract `GameMode` class with `Duel` and `Solo` implementations, and an abstract match repository
- **decorators**: measuring bot thinking time, logging all exceptions to a log file, and registering built-in bots
- **closures**: a closure-based cache for memoizing shortest-path calculations, and callback factories for GUI controls
- **design patterns**: Strategy (bots, game modes), Observer (GUI and storage listening to game events), Command (bot actions), Factory (map generation, bot loading), Repository (match storage)
- **metaprogramming**: validated descriptors for game rule settings, and dynamic loading and inspection of user bot classes
- **doctest and unittest** for map generation, game rules, bot loading and storage
- **PEP 8, PEP 484 and PEP 526**: fully type-annotated code with no errors from the VS Code type checker
