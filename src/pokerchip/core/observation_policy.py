"""Calculation eligibility is separate from observed quality warnings (v6)."""
import math


def usable(row, world=True, time=True, orientation=False):
    if row.get('status') in ('missing', 'outside_interval', 'predicted_only'):
        return False
    if row.get('source') in ('tracking_prediction', 'physics_prediction'):
        return False
    if row.get('assignment_ambiguous') or row.get('identity_status')=='ambiguous' or row.get('observable') is False:
        return False
    if row.get('surface_status') == 'floor_boundary':
        return False
    point = row.get('world_center_m' if world else 'raw_center_px')
    try:
        valid_point=point is not None and len(point)==2 and all(math.isfinite(v) for v in point)
        valid_time=not time or (row.get('physical_time_s') is not None and math.isfinite(row['physical_time_s']))
        valid_orientation=not orientation or (row.get('theta_wrapped_rad') is not None and math.isfinite(row['theta_wrapped_rad']))
    except (TypeError,ValueError):
        return False
    return valid_point and valid_time and valid_orientation


def warnings(row):
    values = list(row.get('calculation_warnings') or [])
    if row.get('measurement_warning'):
        values.append(row['measurement_warning'])
    if row.get('status') in ('low_confidence', 'partially_observed'):
        values.append(row['status'])
    return sorted(set(values))


def warning_audit(rows):
    used = {}
    warned = {}
    reasons_all = set()
    for row in rows:
        reasons_all.update(warnings(row))
        dependencies = row.get('used_observation_refs')
        own = {'chip_id': row.get('chip_id'), 'frame_index': row.get('frame_index')}
        for ref in dependencies if dependencies is not None else [own]:
            key = (ref.get('chip_id'), ref.get('frame_index'))
            if key[0] is None or key[1] is None:
                continue
            used[key] = dict(chip_id=key[0], frame_index=key[1])
        # A derivative's warnings belong to its supporting observations, not
        # automatically to the derivative's target frame.
        inherited = row.get('warning_observation_refs')
        refs = inherited if inherited is not None else ([dict(own, reasons=warnings(row))] if warnings(row) else [])
        for ref in refs:
            key = (ref.get('chip_id'), ref.get('frame_index'))
            if key[0] is None or key[1] is None:
                continue
            used.setdefault(key, dict(chip_id=key[0], frame_index=key[1]))
            warned.setdefault(key, set()).update(ref.get('reasons') or [])
            reasons_all.update(ref.get('reasons') or [])
    refs = [dict(chip_id=k[0], frame_index=k[1], reasons=sorted(v)) for k,v in warned.items() if v]
    total = len(used)
    return {'calculation_warnings': sorted(reasons_all),
            'warning_observation_refs': refs, 'warning_observation_count': len(refs),
            'used_observation_refs': list(used.values()),
            'used_observation_count': total,
            'warning_observation_fraction': len(refs) / total if total else 0.,
            'uses_warned_observations': bool(refs)}
