"""Exercise optional measured context-shape selection; run in each checkout."""
from types import SimpleNamespace
import pandas as pd
from vidur.execution_time_predictor.sklearn_execution_time_predictor import SklearnExecutionTimePredictor
class PredictorFixture(SklearnExecutionTimePredictor):
 def _get_estimator(self): pass
 def _get_grid_search_params(self): pass
p=object.__new__(PredictorFixture)
p._config=SimpleNamespace(kv_cache_prediction_granularity=16)
p._attention_decode_batching_overhead_fraction=0
p._predictions={'attn_decode':{(3,1040):9.0,(3,1056):8.0}}
def batch(lengths):return SimpleNamespace(requests=[SimpleNamespace(_is_prefill_complete=True,num_processed_tokens=n) for n in lengths])
def row(shape,value,context=1040):return {'is_decode':True,'batch_size':3,'kv_cache_size':context,'context_shape':shape,'time_stats.attn_decode.median':value}
p._attention_profile_df=pd.DataFrame([row('unclassified',7),row('uniform',1),row('mixed',2)])
assert p._get_attention_decode_execution_time(batch([1030,1030,1030]))==1
assert p._get_attention_decode_execution_time(batch([1030,1031,1031]))==2
try:p._get_attention_decode_execution_time(batch([1029,1031,1031]));raise AssertionError('unsupported span accepted')
except ValueError as e:assert 'span > 1' in str(e)
p._attention_profile_df=pd.DataFrame([row('uniform',1)])
try:p._get_attention_decode_execution_time(batch([1030,1031,1031]));raise AssertionError('missing shape accepted')
except ValueError as e:assert 'missing attention context shape' in str(e)
p._attention_profile_df=pd.DataFrame([row('unclassified',7)])
assert p._get_attention_decode_execution_time(batch([1030,1031,1031]))==7
assert p._get_attention_decode_execution_time(batch([1050,1050,1050]))==8
p._attention_profile_df=pd.DataFrame([{k:v for k,v in row('uniform',4).items() if k!='context_shape'}])
assert p._get_attention_decode_execution_time(batch([1030,1031,1031]))==4
train=pd.DataFrame([{'is_decode':False,'kv_cache_size':0,'prefill_chunk_size':1024,'prefill_chunk_size_squared':1024**2,'batch_size':1,'context_shape':'unclassified','time_stats.attn_prefill.median':1.0,'time_stats.attn_decode.median':0.0},dict(row('unclassified',7),prefill_chunk_size=0,prefill_chunk_size_squared=0,time_stats_dummy=0,**{'time_stats.attn_prefill.median':0.0}),dict(row('uniform',1),prefill_chunk_size=0,prefill_chunk_size_squared=0,**{'time_stats.attn_prefill.median':0.0}),dict(row('mixed',2),prefill_chunk_size=0,prefill_chunk_size_squared=0,**{'time_stats.attn_prefill.median':0.0})])
p._load_attention_df=lambda _:train.copy();p._attention_input_file='fixture';p._get_attention_df_with_derived_features=lambda x:x
seen={}
def fake_train(**kwargs):seen[kwargs['model_name']]=kwargs['df'].copy();return None
p._train_model=fake_train;p._train_attention_layer_models()
assert len(seen['attn_decode'])==1 and seen['attn_decode'].iloc[0]['context_shape']=='unclassified'
print('PASS: legacy lookup, uniform/mixed selection, unsupported/missing rejection, unclassified fallback, and exclusion of tagged rows from shape-blind training')
if __name__ == '__main__':
 import sys
 if len(sys.argv)>1:
  df=pd.read_csv(sys.argv[1]);df['is_decode']=df['prefill_chunk_size']==0;p._attention_profile_df=df
  tested=0
  for context in range(1040,1153,16):
   for shape,lens in [('uniform',[context-8]*3),('mixed',[context-9,context-8,context-8])]:
    expected=df[(df.context_shape==shape)&(df.batch_size==3)&(df.kv_cache_size==context)]['time_stats.attn_decode.median'];assert len(expected)==1
    assert p._get_attention_decode_execution_time(batch(lens))==float(expected.iloc[0]);tested+=1
  print(f'PASS: {tested} measured candidate cells selected correctly')
