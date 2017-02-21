Highcharts.chart('{{ chart.key }}', {
  chart: {
    type: 'column',
  },

  title: {
    text: '{{ chart.title }}'
  },

  xAxis: {
    categories: {{ chart.data.0.keys|safe }}
  },

  yAxis: {
    allowDecimals: false,
    min: 0,
    title: {
      text: '{{ chart.y_axis }}'
    }
  },

  tooltip: {
    headerFormat: '<span style="font-size:10px">{point.key}</span><table>',
    pointFormat: '<tr><td style="color:{series.color};padding:0">{series.name}: </td>' +
    '<td style="padding:0"><b>{point.y:.0f}</b></td></tr>',
    footerFormat: '</table>',
    shared: true,
    useHTML: true
  },

  plotOptions: {
    column: {
      pointPadding: 0.1,
      borderWidth: 0
    }
  },

  credits: {
    enabled: false
  },

  series: [
  {% for series in chart.data %}
    {
      name: '{{ series.title }}',
      data: {{ series.empty_values|safe }},
      ciMetric: '{{ series.metric }}',
      ciKind: '{{ series.date_range.kind }}',
      ciDate: '{{ series.date_range.date|date:"Ymd" }}',
      ciInteval: '{{ series.interval }}'
    {% if forloop.last %}
    }
    {% else %}
    },
    {% endif %}
  {% endfor %}
  ]
})