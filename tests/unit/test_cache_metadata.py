from pokerchip.config import default_project
from pokerchip.pipeline import stage_keys


def test_launch_exclusions_and_conditions_invalidate_correct_stage():
    p=default_project();e={'id':'e','session_id':'s','name':'a','conditions':'a','interval':[0,None],'participating_chip_ids':['chip_1']}
    a=stage_keys(p,e,'source')
    e['excluded_frame_intervals']=[[2,8]];b=stage_keys(p,e,'source')
    assert a['raw']==b['raw'] and a['analysis']!=b['analysis']
    e['conditions']='corrected note';c=stage_keys(p,e,'source')
    assert c['raw']==b['raw'] and c['analysis']==b['analysis'] and c['export']!=b['export']
    e['last_run']='runs/old';e['status']='complete'
    assert stage_keys(p,e,'source')==c
