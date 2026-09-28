# PitWatch for Home Assistant

Brings a [PitWatch](https://www.pitwatch.app) building into Home Assistant: the
sewage ejector pumps, the pit's floats, the panel alarm, and every alert
PitWatch raises, in the same plain words PitWatch texts people.

PitWatch keeps the logic. The contacts are debounced there, the alert rules run
there, and a pump that overloaded stays marked as shut off until the panel lets
it back in. Home Assistant gets PitWatch's conclusions, pushed the moment they
change, so a pump starting shows up in well under a second.

## What you need

- A PitWatch account with access to the building.
- Home Assistant 2025.3 or newer.

## Install

With [HACS](https://hacs.xyz): open HACS, choose **Custom repositories** from
the menu, add `https://github.com/dkmcgowan/ha-pitwatch` as an
**Integration**, then install **PitWatch** and restart Home Assistant.

By hand: copy `custom_components/pitwatch` into your Home Assistant
`config/custom_components/` folder and restart.

## Make a token

In PitWatch, open your **profile** page and find **Home Assistant and other
apps**.

1. Name it, for example `Home Assistant`.
2. Pick the building.
3. Tick **Allow it to press the panel button** only if you want Home Assistant
   to be able to silence and reset the panel alarm.
4. Press **Make a token** and copy it. It starts with `pw_` and is shown once.

A token is for one building. If you look after two, make two and add the
integration twice. Revoke a token on the same page and Home Assistant stops
receiving data within a minute, then asks for a new one.

## Add the integration

**Settings > Devices & services > Add integration > PitWatch.** Leave the
address as `https://www.pitwatch.app` unless you run your own PitWatch, and
paste the token.

## What you get

One device for the building, named the way PitWatch names it.

| Entity | What it is |
|---|---|
| **Pump 1 running**, **Pump 2 running** | Whether each pump is running. |
| **Pump 1 shut off**, **Pump 2 shut off** | A pump that shut itself off to protect its motor, until the panel puts it back in service. |
| **Pump 1 current**, **Pump 2 current** | What each motor is drawing, in amps. |
| **Pump 1 runs today**, **Pump 2 runs today** | How many times each pump has run since midnight at the building. |
| **Pump 1 last run**, **Pump 2 last run** | How long the last run took. |
| **Pump 1 panel display**, **Pump 2 panel display** | LEAD, LAG, ON or ERROR, the words on the controller's own display. |
| **High water** | The water in the pit has reached the alarm level. |
| **Lead float**, **Lag float** | The two floats that start the pumps. |
| **Panel alarm** | The pump controller's own alarm is sounding. |
| **Both pumps running** | Water is coming in faster than one pump can handle. |
| **Needs attention** | On while PitWatch has any warning or critical alert open. The open alerts are listed on it. |
| **Open alerts** | How many alerts are open. |
| **Alerts** | An event that fires every time an alert is raised or cleared. |
| **Rain in the last 24 hours**, **next 24 hours**, **last 7 days**, **Chance of rain** | The weather at the building, which is usually why the pit is busy. |
| **Silence panel alarm**, **Reset panel alarm** | Buttons, only if the building has the panel button wired and the token may press it. |

Under diagnostics: whether PitWatch can hear each device at the building, the
usual current for each pump, and whether the live connection to PitWatch is up.

## Automations

Every alert fires the **Alerts** event entity and a `pitwatch_alert` event on
the event bus. Both carry the alert's `message`, its `title`, its `severity`
(`info`, `warning` or `critical`), and whether it was `raised` or `cleared`.

Send every PitWatch alert to your phone:

```yaml
automation:
  - alias: PitWatch alerts to my phone
    triggers:
      - trigger: event
        event_type: pitwatch_alert
    actions:
      - action: notify.mobile_app_your_phone
        data:
          title: "PitWatch: {{ trigger.event.data.title }}"
          message: "{{ trigger.event.data.message }}"
```

Say critical ones out loud, only when they are raised:

```yaml
automation:
  - alias: PitWatch critical alerts on the kitchen speaker
    triggers:
      - trigger: event
        event_type: pitwatch_alert
        event_data:
          event: raised
          severity: critical
    actions:
      - action: tts.speak
        target:
          entity_id: tts.home_assistant_cloud
        data:
          media_player_entity_id: media_player.kitchen
          message: "{{ trigger.event.data.message }}"
```

## How it stays current

The integration holds a live connection to PitWatch, which sends the whole
state when it connects and after that only what changes, plus each alert as it
happens. Nothing is polled while that connection is up. If it drops, the
integration asks once a minute until it reconnects, and announces any alert that
was raised or cleared while it was down. Alerts from before Home Assistant
started are not announced again.

## License

MIT. See [LICENSE](LICENSE).
