"""Public, deterministic event projection of a trusted replay.

Never serialize replay info: open-mode info contains evaluator-only scores.
This is an artifact encoder, not a security boundary for arbitrary environments.
"""
import copy


def public_events(actions, replay):
    """Reset has step -1; action steps use the actions-v1 zero-based indices.

    Page tokens become {from_step: index}, referring to the response that
    supplied the cursor. All other public observations are preserved verbatim.
    Partial trajectories are supported. Caller supplies a matching trusted replay.
    """
    if len(actions) != len(replay['steps']):
        raise ValueError('action and response counts differ')
    episode_id = replay['initial']['manifest']['episode_id']

    def event(step, action, observation, reward, terminated, truncated):
        return copy.deepcopy({
            'event_format': 'ledgergym-events-v1', 'episode_id': episode_id,
            'step': step, 'action': action, 'observation': observation,
            'reward': reward, 'terminated': terminated, 'truncated': truncated,
        })

    events = [event(-1, None, replay['initial'], 0.0, False, False)]
    for index, (action, response) in enumerate(zip(actions, replay['steps'])):
        observation, reward, terminated, truncated, _ = response
        row = event(index, action, observation, reward, terminated, truncated)
        if (isinstance(action, dict) and action.get('action') == 'list_records'
                and isinstance(row['observation'].get('next_cursor'), str)):
            row['observation']['next_cursor'] = {'from_step': index}
        events.append(row)
    return events
