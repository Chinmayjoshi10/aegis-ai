from typing import Any

import pandas as pd


class DataUnderstandingLayer:
    def run(self, df: pd.DataFrame) -> dict[str, list[Any]]:
        df = df.loc[:, ~df.columns.duplicated()]
        numeric_columns = list(df.select_dtypes(include="number").columns)
        metric_scores = []

        for column in numeric_columns:
            series = df[column].dropna()
            if series.empty:
                variance = 0.0
                coefficient_of_variation = 0.0
            else:
                variance = float(series.var())
                mean = float(series.mean())
                std = float(series.std())
                coefficient_of_variation = std / abs(mean) if mean else 0.0
            if variance < 1e-6:
                continue
            metric_scores.append((column, variance + coefficient_of_variation))

        metric_scores.sort(key=lambda item: (-item[1], item[0]))
        key_metrics = [column for column, _ in metric_scores[:5]]

        important_dimensions = []
        if key_metrics:
            top_metric = key_metrics[0]
            categorical_columns = list(
                df.select_dtypes(include=["object", "category", "bool"]).columns
            )
            dimension_scores = []

            for column in categorical_columns:
                if df[column].nunique() > len(df) * 0.5:
                    continue

                grouped_means = df.groupby(column, dropna=True)[top_metric].mean()
                score = 0.0 if grouped_means.empty else float(grouped_means.var())
                dimension_scores.append((column, score))

            dimension_scores.sort(key=lambda item: (-item[1], item[0]))
            important_dimensions = [column for column, _ in dimension_scores[:3]]

        relationships = []
        if len(key_metrics) > 1:
            correlations = df[key_metrics].corr()
            for index, left in enumerate(key_metrics):
                for right in key_metrics[index + 1 :]:
                    correlation_raw: Any = correlations.at[left, right]
                    correlation_value = float(correlation_raw)
                    if pd.isna(correlation_value):
                        continue
                    if abs(correlation_value) > 0.5:
                        relationships.append(
                            {
                                "metric_1": left,
                                "metric_2": right,
                                "correlation": correlation_value,
                            }
                        )

        return {
            "key_metrics": key_metrics,
            "important_dimensions": important_dimensions,
            "relationships": relationships,
        }
