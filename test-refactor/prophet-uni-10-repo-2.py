# Databricks notebook source
# MAGIC %md
# MAGIC # Prophet training
# MAGIC This is an auto-generated notebook. To reproduce these results, attach this notebook to the **wenfei-mlr-10-0** cluster and rerun it.
# MAGIC - Compare trials in the [MLflow experiment](#mlflow/experiments/2870319524883785/s?orderByKey=metrics.%60val_smape%60&orderByAsc=true)
# MAGIC - Navigate to the parent notebook [here](#notebook/2870319524883784) (If you launched the AutoML experiment using the Experiments UI, this link isn't very useful.)
# MAGIC - Clone this notebook into your project folder by selecting **File > Clone** in the notebook toolbar.
# MAGIC 
# MAGIC Runtime Version: _10.0.x-cpu-ml-scala2.12_

# COMMAND ----------

import mlflow
import databricks.automl_runtime

# Use MLflow to track experiments
mlflow.set_experiment("/Users/wenfei.yan@databricks.com/databricks_automl/Temp_daily_min_temperatures-2021_11_12-16_52")

target_col = "Temp"
time_col = "Date"
unit = "D"

horizon = 1

# COMMAND ----------

# MAGIC %md
# MAGIC ## Load Data

# COMMAND ----------

from mlflow.tracking import MlflowClient
import os
import uuid
import shutil
import pyspark.pandas as ps

# Create temp directory to download input data from MLflow
input_temp_dir = os.path.join("/dbfs/tmp/", str(uuid.uuid4())[:8])
os.makedirs(input_temp_dir)

# Download the artifact and read it into a pandas DataFrame
input_client = MlflowClient()
input_data_path = input_client.download_artifacts("7a00dc8594554161af538682a1850b1f", "data", input_temp_dir)

input_file_path = os.path.join(input_data_path, "training_data")
input_file_path = "file://" + input_file_path
df_loaded = ps.read_parquet(input_file_path)

# Preview data
df_loaded.head(5)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Train Prophet model
# MAGIC - Log relevant metrics to MLflow to track runs
# MAGIC - All the runs are logged under [this MLflow experiment](#mlflow/experiments/2870319524883785/s?orderByKey=metrics.%60val_smape%60&orderByAsc=true)
# MAGIC - Change the model parameters and re-run the training cell to log a different trial to the MLflow experiment

# COMMAND ----------

# MAGIC %md
# MAGIC ### Aggregate data by `target_col`

# COMMAND ----------

group_cols = [time_col]
df_aggregation = df_loaded \
  .groupby(group_cols) \
  .agg(y=(target_col, "avg")) \
  .reset_index() \
  .rename(columns={ time_col : "ds" })

print(df_aggregation.count())
df_aggregation.head()

# COMMAND ----------

# Start MLflow run
import mlflow
mlflow_run = mlflow.start_run(run_name="PROPHET")
run_id = mlflow_run.info.run_id

# COMMAND ----------

import logging
import pandas as pd

# disable informational messages from fbprophet
logging.getLogger("py4j").setLevel(logging.WARNING)

result_columns = ["model_json", "mse", "rmse", "mae", "mape", "mdape", "smape", "coverage"]

def generate_cutoffs(model, horizon: pd.Timedelta, num_folds: int):
  """Generate cutoff dates
  Parameters
  ----------
  model: Prophet class object. Fitted Prophet model.
  horizon: pd.Timedelta forecast horizon.
  num_folds: int number of cutoffs for cross validation.
f
  Returns
  -------
  list of pd.Timestamp
  """
  period = 0.5 * horizon

  period_max = max([s["period"] for s in model.seasonalities.values()]) if model.seasonalities else 0.
  seasonality_dt = pd.Timedelta(str(period_max) + " days")

  initial = max(3 * horizon, seasonality_dt)

  df = model.history.copy().reset_index(drop=True)

  # Last cutoff is "latest date in data - horizon" date
  cutoff = df["ds"].max() - horizon
  if cutoff < df["ds"].min():
      raise ValueError("Less data than horizon.")
  result = [cutoff]
  while result[-1] >= min(df["ds"]) + initial and len(result) < num_folds:
      cutoff -= period
      # If data does not exist in data range (cutoff, cutoff + horizon]
      if not (((df["ds"] > cutoff) & (df["ds"] <= cutoff + horizon)).any()):
          # Next cutoff point is "last date before cutoff in data - horizon"
          if cutoff > df["ds"].min():
              closest_date = df[df["ds"] <= cutoff].max()["ds"]
              cutoff = closest_date - horizon
          # else no data left, leave cutoff as is, it will be dropped.
      result.append(cutoff)
  result = result[:-1]
  if len(result) == 0:
      raise ValueError(
          "Less data than horizon after initial window. "
          "Make horizon or initial shorter."
      )
  return list(reversed(result))

def prophet_training(history_pd):
  from mlflow.tracking import MlflowClient
  import numpy as np
  import pandas as pd
  from prophet import Prophet
  from prophet.serialize import model_to_json
  from hyperopt import fmin, hp, STATUS_OK, tpe, SparkTrials
 
  # Define training function for hyperparameter tuning with hyperopt
  def prophet_fit_predict(params):
    import pandas as pd
    from prophet import Prophet
    from prophet.diagnostics import cross_validation, performance_metrics

    changepoint_prior_scale = params["changepoint_prior_scale"]
    seasonality_prior_scale = params["seasonality_prior_scale"]
    holidays_prior_scale = params["holidays_prior_scale"]
    seasonality_mode = params["seasonality_mode"]

    model = Prophet(changepoint_prior_scale=changepoint_prior_scale,
                seasonality_prior_scale=seasonality_prior_scale,
                holidays_prior_scale=holidays_prior_scale,
                seasonality_mode=seasonality_mode,
                interval_width=0.8)
    model.fit(history_pd, iter=200)

    # Evaluate Metrics
    horizon_timedelta = pd.to_timedelta(horizon, unit=unit)
    cutoffs = generate_cutoffs(model, horizon=horizon_timedelta, num_folds=20)
    df_cv = cross_validation(model, horizon=horizon_timedelta, cutoffs=cutoffs, disable_tqdm=True)
    df_metrics = performance_metrics(df_cv)

    metrics = {
      "mse": df_metrics["mse"].mean(),
      "rmse": df_metrics["rmse"].mean(),
      "mae": df_metrics["mae"].mean(),
      # prophet doesn't calculate mape if any y is close to 0
      "mape": df_metrics["mape"].mean() if "mape" in df_metrics else np.nan,
      "mdape": df_metrics["mdape"].mean(),
      "smape": df_metrics["smape"].mean(),
      # prophet doesn't calculate coverage if df_cv doesn't include yhat_lower or yhat_upper
      "coverage": df_metrics["coverage"].mean() if "coverage" in df_metrics else np.nan
    }

    return {"loss": metrics["smape"], "metrics": metrics, "status": STATUS_OK}


  seasonality_mode = ["additive", "multiplicative"]
  search_space =  {
    "changepoint_prior_scale": hp.loguniform("changepoint_prior_scale", -6.9, -0.69),
    "seasonality_prior_scale": hp.loguniform("seasonality_prior_scale", -6.9, 2.3),
    "holidays_prior_scale": hp.loguniform("holidays_prior_scale", -6.9, 2.3),
    "seasonality_mode": hp.choice("seasonality_mode", seasonality_mode)
  }

  algo=tpe.suggest

  trials = SparkTrials()
  spark.conf.set("spark.databricks.mlflow.trackHyperopt.enabled", "false")
 
  best_result = fmin(
    fn=prophet_fit_predict,
    space=search_space,
    algo=algo,
    max_evals=10,
    trials=trials,
    timeout=7140,
    rstate = np.random.RandomState(189400784))

  spark.conf.set("spark.databricks.mlflow.trackHyperopt.enabled", "true")
  
  # Retrain the model with all history data.
  model = Prophet(changepoint_prior_scale=best_result["changepoint_prior_scale"],
                seasonality_prior_scale=best_result["seasonality_prior_scale"],
                holidays_prior_scale=best_result["holidays_prior_scale"],
                seasonality_mode=seasonality_mode[best_result["seasonality_mode"]],
                interval_width=0.8)
  model.fit(history_pd)

  model_json = model_to_json(model)
  metrics = trials.best_trial["result"]["metrics"]

  results_pd = pd.DataFrame({"model_json": model_json}, index=[0])
  results_pd.reset_index(level=0, inplace=True)
  results_pd["mse"] = metrics["mse"]
  results_pd["rmse"] = metrics["rmse"]
  results_pd["mae"] = metrics["mae"]
  results_pd["mape"] = metrics["mape"]
  results_pd["mdape"] = metrics["mdape"]
  results_pd["smape"] = metrics["smape"]
  results_pd["coverage"] = metrics["coverage"]
  results_pd["prophet_params"] = str(best_result)

  return results_pd[result_columns]

# COMMAND ----------

from prophet import Prophet
history_pd = df_aggregation.to_pandas()
model = Prophet(changepoint_prior_scale=changepoint_prior_scale,
            seasonality_prior_scale=seasonality_prior_scale,
            holidays_prior_scale=holidays_prior_scale,
            seasonality_mode=seasonality_mode,
            interval_width=0.8)
model.fit(history_pd, iter=200)
horizon_timedelta = pd.to_timedelta(horizon, unit=unit)
cutoffs = generate_cutoffs(model, horizon=horizon_timedelta, num_folds=20)

# COMMAND ----------

from mlflow.tracking import MlflowClient

client = MlflowClient()
client.log_param(run_id, "interval_width", 0.8)

forecast_results = prophet_training(df_aggregation.to_pandas())

# COMMAND ----------

# MAGIC %md
# MAGIC ### Display the results and log them to MLflow

# COMMAND ----------

forecast_results

# COMMAND ----------

avg_metrics = forecast_results[["mse", "rmse", "mae", "mape", "mdape", "smape", "coverage"]].mean()
mlflow.log_metric("val_mse", avg_metrics["mse"])
mlflow.log_metric("val_rmse", avg_metrics["rmse"])
mlflow.log_metric("val_mae", avg_metrics["mae"])
mlflow.log_metric("val_mape", avg_metrics["mape"])
mlflow.log_metric("val_mdape", avg_metrics["mdape"])
mlflow.log_metric("val_smape", avg_metrics["smape"])
mlflow.log_metric("val_coverage", avg_metrics["coverage"])

# COMMAND ----------

# MAGIC %md
# MAGIC ### Save the model

# COMMAND ----------

import cloudpickle
import mlflow
import prophet

class ProphetWrapper(mlflow.pyfunc.PythonModel):
  def __init__(self, model_json, horizon):
    self._model_json = model_json
    self._horizon = horizon
    super().__init__()

  def load_context(self, context):
    from prophet import Prophet
    return

  def model(self):
    from prophet.serialize import model_from_json
    return model_from_json(self._model_json)

  def _make_future_dataframe(self, horizon):
    return self.model().make_future_dataframe(periods=horizon, freq=unit)

  def _predict_impl(self, horizon=None):
    future_pd = self._make_future_dataframe(horizon=horizon or self._horizon)
    return self.model().predict(future_pd)

  def predict_timeseries(self, horizon=None):
    return self._predict_impl(horizon)

  def predict(self, context, input):
    return self._predict_impl()


conda_env = {
    "channels": ["conda-forge"],
    "dependencies": [
        {
            "pip": [
                f"prophet=={prophet.__version__}",
                f"cloudpickle=={cloudpickle.__version__}",
            ]
        }
    ],
    "name": "fbp_env",
}

# COMMAND ----------

model_json = forecast_results["model_json"].to_list()[0]
prophet_model = ProphetWrapper(model_json, horizon)
mlflow.pyfunc.log_model("model", conda_env=conda_env, python_model=prophet_model)
mlflow.end_run()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Analyze the predicted results

# COMMAND ----------

#Load the model
prophet_model = mlflow.pyfunc.load_model(f"runs:/{run_id}/model")

# Predict future with the default horizon
forecast_pd = prophet_model._model_impl.python_model.predict_timeseries()

print(forecast_pd.shape)
forecast_pd.head()

# COMMAND ----------

# MAGIC %md
# MAGIC ### Plot the forecast with change points and trend

# COMMAND ----------

from prophet.plot import plot_plotly, plot_components_plotly

model = prophet_model._model_impl.python_model.model()
fig = plot_plotly(model, forecast_pd, changepoints=True, trend=True, figsize=(1200, 600))
fig

# COMMAND ----------

# MAGIC %md
# MAGIC ### Plot the forecast components

# COMMAND ----------

fig = plot_components_plotly(model, forecast_pd, figsize=(900, 400))
fig.show()

# COMMAND ----------


