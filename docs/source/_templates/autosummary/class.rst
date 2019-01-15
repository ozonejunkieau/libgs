{# Ref: http://www.sphinx-doc.org/en/master/usage/extensions/autosummary.html #}

{{ fullname | escape | underline}}

.. currentmodule:: {{ module }}

.. autoclass:: {{ objname }}

   {% block methods %}

   {% if methods %}
   .. rubric:: Methods

   {# Customized from original by adding toctree. This generates docs for the
   listed functions. #}
   .. autosummary::
      :toctree: .
   {% for item in methods %}
      {% if item != '__init__' %}
      {%- if item not in inherited_members %}
      ~{{ name }}.{{ item }}
      {%- endif %}
      {% endif %}
   {%- endfor %}
   {% endif %}
   {% endblock %}

   {% block attributes %}
   {% if attributes %}
   .. rubric:: Attributes
   
   .. autosummary::
      :toctree: .
   {% for item in attributes %}
      {%- if item not in inherited_members %}
      ~{{ name }}.{{ item }}
      {%- endif %}
   {%- endfor %}
   {% endif %}
   {% endblock %}


   {% block inherited %}
   {% if inherited_members %}

   .. rubric:: Inherited from base class

   .. autosummary::
      :toctree: .
   {% for item in methods %}
      {% if item != '__init__' %}
      {%- if item in inherited_members %}
      ~{{ name }}.{{ item }}
      {%- endif %}
      {% endif %}
   {%- endfor %}   
   {% for item in attributes %}
      {%- if item in inherited_members %}
      ~{{ name }}.{{ item }}
      {%- endif %}
   {%- endfor %}
   {% endif %}

   {% endblock %}


