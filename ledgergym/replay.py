"""Trusted local replay of portable actions; not an agent security boundary."""
import copy


def replay_actions(env, actions, *, seed=None, config=None):
    """Resolve cursor {from_step: index} against this run's page responses.

    Indices are zero-based. Literal cursor tokens cannot be replayed after reset.
    All other action fields (including episode_id) pass through unchanged.
    Partial trajectories are allowed. Returned scores follow the env's mode.
    """
    actions = copy.deepcopy(actions)
    initial, info = env.reset(seed=seed, config=config)
    steps = []
    for recorded in actions:
        action = copy.deepcopy(recorded)
        if steps and (steps[-1][2] or steps[-1][3]):
            raise ValueError('trajectory continues after termination')
        if isinstance(action, dict) and action.get('action') == 'list_records' and action.get('cursor') is not None:
            ref = action['cursor']
            if not isinstance(ref, dict) or set(ref) != {'from_step'}:
                raise ValueError('expected portable cursor reference')
            index = ref['from_step']
            if type(index) is not int or not 0 <= index < len(steps):
                raise ValueError('cursor reference must name an earlier step')
            source = actions[index]
            token = steps[index][0].get('next_cursor')
            if (not isinstance(source, dict) or source.get('action') != 'list_records'
                    or source.get('table') != action.get('table') or not isinstance(token, str)):
                raise ValueError('referenced step did not return a cursor for this table')
            action['cursor'] = token
        steps.append(env.step(action))
    return {'initial': initial, 'info': info, 'steps': steps}
