# Changelog

## [0.1.0]

**The first release.** Brings one PitWatch building into Home Assistant,
pushed as it changes.

- Each pump: running, shut off, current, runs today, last run, and the word on
  the controller's display (LEAD, LAG, ON, ERROR).
- The pit: high water, the lead and lag floats, the panel alarm, and both pumps
  running at once.
- **Needs attention**, on while PitWatch has a warning or critical alert open,
  with the open alerts listed on it.
- **Alerts**, an event entity that fires for every alert raised or cleared with
  the same plain sentence PitWatch texts people, and the same thing on the
  event bus as `pitwatch_alert`.
- Rain at the building: the last 24 hours, the next 24 hours, the last 7 days,
  and the chance of rain.
- **Silence panel alarm** and **Reset panel alarm**, when the building has the
  panel button wired and the token was made able to press it.

Needs PitWatch 0.146.0 or newer, and a token made on the PitWatch profile page.
