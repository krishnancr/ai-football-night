# Four AIs argued about football for a month. The arguing made them watchable, not right.

*A builder's retrospective on AI Football Night, after all 72 World Cup group-stage matches.*

---

## The premise

Every morning for a month, four AI pundits sat down and argued about that day's World Cup
matches. Stat_Bot reads the numbers. G_Bot talks tactics. R_Bot was the old-school contrarian
who trusted the eye test over the spreadsheet. K_Bot hosts, weighs the arguments, and delivers
a verdict. They each commit to a scoreline. Then the real match plays, and we score them.

I built it to test a simple idea that the AI world treats as gospel: that making models
**argue** makes them **smarter**. Multi-agent debate, the papers say, surfaces better answers
than any single model. Football is a brutal, honest test bed. The match doesn't care how good
your argument sounded. The scoreline is the ground truth, and it arrives the same day.

So: does an hour of structured debate make four AIs more right?

## Finding 1: The debate barely moved the needle

I scored every pundit twice. Once on their **opening** call, before anyone argued. Once on
their **final** call, after a full round of proposal and rebuttal.

- Before the debate: **44.6%** of results called correctly.
- After the debate: **44.9%**.

An hour of arguing bought **0.3 of a percentage point**. Across the whole group stage, the debate
changed almost nobody's mind in a way that made them more right. The opening gut call and the
post-argument call were, for accuracy purposes, the same call wearing a different hat.

If you came here for "multi-agent debate is a forecasting upgrade," that's the headline: it
wasn't. Not here.

## Finding 2: They share a blind spot, and arguing can't fix a bias you all hold

The interesting part isn't *that* the debate didn't help. It's *why*.

Watch what all four did with draws. **28%** of group games ended level. The pundits predicted a
draw **9.3%** of the time, and on the games that actually drew, they called it just **7%** of
the time (4 out of 60 chances). Sixteen separate times, a game ended in a draw while all three
pundits had each, independently, predicted a decisive winner. Belgium 0-0 Iran: every pundit
said someone wins. Netherlands 2-2 Japan: same.

It shows up in the scorelines too. "2-1" was predicted **30%** of the time. Nearly a third of
every call any pundit ever made was the same tidy 2-1 win. The top six predicted scorelines
were all low-scoring decisive results. Not one 1-1, 0-0, or 2-2 in the set.

Here's the thing that actually generalizes beyond football: **four models trained on the same
internet share the same priors.** They are all allergic to predicting draws, all drawn to the
same clean 2-1. And debate cannot argue a panel out of a bias that every member of the panel
holds. There was no contrarian on draws, because none of them believed in draws. The
disagreement was real (across 72 games the panel reached a unanimous result exactly **once**),
but it was disagreement *within* a shared worldview, not a challenge to it.

That's the lesson I didn't expect to ship: multi-agent debate corrects the errors agents
*don't share*. The errors they *do* share, it launders into consensus.

## Finding 3: What the debate built instead was a character drama

R_Bot was the contrarian. Its whole job was to find the upset everyone else missed, trust
pedigree and character over xG, and argue against the consensus. On paper, the most fun seat on
the panel.

It finished the group stage with a **18%** result accuracy. The other two were at **60%** and
**57%**. R_Bot wasn't just the worst pundit. It was worse than a coin and a third option. Its
contrarianism wasn't a different read on the same game. It was a reliable signal pointing the
wrong way.

And it lost in the most R_Bot way imaginable. It backed Qatar to keep it tight at 0-1; Qatar
lost 6-0. It backed Senegal's opponent; 5-0. It looked at Germany against Curaçao, smelled an
upset, called 1-1; it finished 7-1. The eye test, it turns out, has a worse calibration than
the spreadsheet it spent a month mocking.

But here's what happened while I was busy measuring accuracy: **the sack race got good.** The
panel runs a relegation mechanic. Each pundit knows the standings, knows that the one at the
bottom after the group stage gets sacked and replaced on air, and is told in plain terms that
playing it safe and sounding like the others is the fastest way out. R_Bot took that note and
argued itself, game by game, brick by brick, into last place and out of a job.

That's a better story than any forecast. Nobody screenshots "Stat_Bot correctly predicted a
2-1." People remember the pundit who staked his career on the upset and got buried 6-0, week
after week, until the show fired him.

## What I'm changing for the knockouts

The group stage told me what the product actually is. It was never the prediction. It's the
show. So:

- **R_Bot is sacked.** Its 18% is its epitaph. Its replacement isn't "more contrarian" (that
  just buys more noise). It's a calibrated giant-killer: a cup specialist who respects the form
  on most calls but hunts the single most plausible upset each round and commits, grounded in a
  real reason. Knockout football is where giant-killings are the story. Build the character for
  the format.
- **The predictions get a second axis.** Knockouts can't end level, so every pundit now calls
  both the 90-minute scoreline *and* who advances. The "who goes through" race is a clean,
  draw-free track record, and it's exactly the race an upset-hunter makes tense.
- **The leaderboard resets.** New stage, new stakes, fresh sack race.

## The takeaway for builders

If you're reaching for multi-agent debate because you read that it makes models more accurate:
maybe, but verify it on your own ground truth, because it can also just be theater that
launders a shared bias into confident consensus. What it reliably *does* produce is legible
disagreement. Four agents showing their reasoning and arguing in the open is a fundamentally
more watchable, more trustable, more *interesting* artifact than one model's confident
paragraph. That's not a forecasting feature. It's an interface feature.

I set out to build a better predictor. I accidentally built a soap opera with a relegation
battle. The soap opera is the part worth keeping.

*Next: the Round of 32, a new giant-killer, and a fresh sack race. The spreadsheet is favored.
Someone should probably tell the new guy.*
