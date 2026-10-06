{# Echoue pour chaque ligne dont le prix au m2 sort de la plage plausible (variables du projet). #}
{% test prix_m2_plausible(model, column_name) %}
select {{ column_name }}
from {{ model }}
where {{ column_name }} < {{ var('prix_m2_min') }}
   or {{ column_name }} > {{ var('prix_m2_max') }}
{% endtest %}
