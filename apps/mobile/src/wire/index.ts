/**
 * The shape the server sends, written out to match `services/api/views.py`.
 *
 * Hand-written, like the Python side it mirrors, and for the same reason: the
 * wire is a contract two people agreed on, not a dump of either side's types.
 * `tests/api/test_wire_contract.py` reads this folder and fails if the server
 * starts sending a field these do not know about, which is the drift that would
 * otherwise be found by a blank space in the UI.
 *
 * Nothing here interprets anything. `reasons` are sentences the engine wrote
 * and this app prints; it does not know what a land is, and must not learn.
 *
 * Split in four: `game` is the board and how it ended, `board` is what the
 * engine computed about it and is certainly true, `claude` is what a model said
 * and had to be checked, and `replay` is a game that already happened.
 * Importers do not care -- `from "./wire"` still reaches all of it.
 */

export * from "./board";
export * from "./game";
export * from "./claude";
export * from "./replay";
