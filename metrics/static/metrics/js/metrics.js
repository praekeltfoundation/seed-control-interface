function updateAllCharts(base_url, charts) {
  $.each(charts, function(chart_type, chart) {
    if (chart != null) {
      $.each(chart.series, function(index, series) {
        $.get(base_url + '?metric=' + series.options.ciMetric + '&kind=' + series.options.ciKind + '&date=' + series.options.ciDate + '&interval=' + series.options.ciInteval, function(data) {
          console.log(data);
          chart.series[index].setData(data['values']);
        });
      });
    }
  });
};