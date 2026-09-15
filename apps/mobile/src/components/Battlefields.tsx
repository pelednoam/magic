/**
 * Both battlefields, which are always shown together and always in this order.
 *
 * Yours first because it is the one you act on: tapping a permanent here is how
 * you pay for things. Theirs is read-only — a tracker that let you tap the
 * other player's lands would be a tracker that let you cheat with them.
 */

import { Board } from "./Board";

import type { Permanent, Player } from "../wire";

export function Battlefields({
  mine,
  theirs,
  seat,
  onTap,
}: {
  readonly mine: Player;
  readonly theirs: Player;
  readonly seat: string;
  /**
   * How to apply an event. Absent when nothing can be done — a game that has
   * ended, where the server refuses everything.
   *
   * Taking the applier rather than a ready-made handler keeps the one thing
   * tapping a permanent *means* in the component that draws the permanents:
   * it flips `tapped`, and the screen does not need to know that.
   */
  readonly onTap?: ((event: Record<string, unknown>) => void) | undefined;
}) {
  return (
    <>
      <Board
        title="Your battlefield"
        player={mine}
        onTap={
          onTap === undefined
            ? undefined
            : (permanent: Permanent) => {
                onTap({
                  type: "set_tapped",
                  player: seat,
                  instance_id: permanent.instance_id,
                  tapped: !permanent.tapped,
                });
              }
        }
      />
      <Board title="Their battlefield" player={theirs} />
    </>
  );
}
