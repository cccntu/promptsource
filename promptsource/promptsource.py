import datasets
import random
import streamlit as st

from session_state import get as get_session_state
from templates import Template, TemplateCollection


MAX_SIZE = 100000000

#
# Helper functions for datasets library
#

@st.cache(allow_output_mutation=True)
def get_dataset(path, conf=None):
    "Get a dataset from name and conf."
    module_path = datasets.load.prepare_module(path, dataset=True)
    builder_cls = datasets.load.import_main_class(module_path[0], dataset=True)
    if conf:
        builder_instance = builder_cls(name=conf, cache_dir=None)
    else:
        builder_instance = builder_cls(cache_dir=None)
    fail = False
    if (
        builder_instance.manual_download_instructions is None
        and builder_instance.info.size_in_bytes is not None
        and builder_instance.info.size_in_bytes < MAX_SIZE):
        builder_instance.download_and_prepare()
        dts = builder_instance.as_dataset()
        dataset = dts
    else:
        dataset = builder_instance
        fail = True
    return dataset, fail


@st.cache
def get_dataset_confs(path):
    "Get the list of confs for a dataset."
    module_path = datasets.load.prepare_module(path, dataset=True)
    # Get dataset builder class from the processing script
    builder_cls = datasets.load.import_main_class(module_path[0], dataset=True)
    # Instantiate the dataset builder
    confs = builder_cls.BUILDER_CONFIGS
    if confs and len(confs) > 1:
        return confs
    return []


def render_features(features):
    if isinstance(features, dict):
        return {k: render_features(v) for k, v in features.items()}
    if isinstance(features, datasets.features.ClassLabel):
        return features.names

    if isinstance(features, datasets.features.Value):
        return features.dtype

    if isinstance(features, datasets.features.Sequence):
        return {"[]": render_features(features.feature)}
    return features


st.set_page_config(layout="wide")

st.sidebar.title("PromptSource 🌸")

#
# Loads template data
#
try:
    with open("./templates.yaml", 'r') as f:
        templates = TemplateCollection.read_from_file(f)
except FileNotFoundError:
    st.error("Unable to load the templates file!\n\n"
             "We expect the file templates.yaml to be in the working directory. "
             "You might need to restart the app in the root directory of the repo.")
    st.stop()


def save_data(message="Done!"):
    with open("./templates.yaml", 'w') as f:
        templates.write_to_file(f)
        st.success(message)


#
# Loads dataset information
#
dataset_list = datasets.list_datasets()

#
# Initializes state
#
session_state = get_session_state(example_index=0, dataset=dataset_list[0])
#
# Select a dataset
#
# TODO: Currently raises an error if you select a dataset that requires a
# TODO: configuration. Not clear how to query for these options.
dataset_key = st.sidebar.selectbox('Dataset', dataset_list, key='dataset_select',
                 help='Select the dataset to work on. Number in parens ' +
                      'is the number of prompts created.')
st.sidebar.write("HINT: Try ag_news or trec for examples.")

#
# If a particular dataset is selected, loads dataset and template information
#
if dataset_key is not None:

    #
    # Check for subconfigurations
    #
    configs = get_dataset_confs(dataset_key)
    conf_avail = len(configs) > 0
    conf_option = None
    if conf_avail:
        start = 0
        conf_option = st.sidebar.selectbox(
            "Subset", configs, index=start, format_func=lambda a: a.name
        )

    dataset, _ = get_dataset(dataset_key, str(conf_option.name) if conf_option else None)



    k = list(dataset.keys())
    index = 0
    if "train" in dataset.keys():
        index = k.index("train")
    split = st.sidebar.selectbox("Split", k, index=index)
    dataset = dataset[split]
    session_state.example_index = random.randint(0, len(dataset))
            
    #
    # Display dataset information
    #
    st.header(
        "Dataset: "
        + dataset_key
        + " "
        + (("/ " + conf_option.name) if conf_option else "")
    )

    st.markdown(
        "*Homepage*: "
        + dataset.info.homepage
        + "\n\n*Dataset*: https://github.com/huggingface/datasets/blob/master/datasets/%s/%s.py"
        % (dataset_key, dataset_key)
    )

    md = """
    %s
    """ % (
        dataset.info.description.replace("\\", "") if dataset_key else ""
    )
    st.markdown(md)

    st.sidebar.subheader("Dataset Schema")
    st.sidebar.write(render_features(dataset.features))

    with st.form("example_form"):
        st.sidebar.subheader("Random Training Example")
        new_example_button = st.sidebar.button("New Example", key="new_example")
        if new_example_button or dataset_key != session_state.dataset:
            session_state.example_index = random.randint(0, len(dataset))
            session_state.dataset = dataset_key
        example = dataset[session_state.example_index]
        st.sidebar.write(example)

    col1, _, col2 = st.beta_columns([18, 1, 6])

    template_key = dataset_key
    if conf_option:
        template_key = (dataset_key, conf_option.name)

    with col1:
        with st.beta_expander("Select Template", expanded=True):
            with st.form("new_template_form"):
                new_template_input = st.text_input("New Template Name", key="new_template_key", value="",
                                                   help="Enter name and hit enter to create a new template.")
                new_template_submitted = st.form_submit_button("Create")
                if new_template_submitted:
                    new_template_name = new_template_input
                    if new_template_name in templates.get_templates(template_key):
                        st.error(f"A template with the name {new_template_name} already exists "
                                 f"for dataset {template_key}.")
                    elif new_template_name == "":
                        st.error(f"Need to provide a template name.")
                    else:
                        template = Template(new_template_name, '', 'return ""', 'return ""', '')
                        templates.add_template(template_key, template)
                        save_data()
                else:
                    new_template_name = None

            dataset_templates = templates.get_templates(template_key)
            template_list = list(dataset_templates.keys())
            if new_template_name:
                index = template_list.index(new_template_name)
            else:
                index = 0
            template_name = st.selectbox('', template_list, key='template_select',
                                          index=index, help='Select the template to work on.')

            if st.button("Delete Template", key="delete_template"):
                templates.remove_template(template_key, template_name)
                save_data("Template deleted!")



        if template_name is not None:
            template = dataset_templates[template_name]
            #
            # If template is selected, displays template editor
            #
            editor = st.radio("Editor Type", ["Code", "Jinja"], 1 if template.jinja_tpl else 0)

            if editor == "Code":
                with st.form("edit_template_form"):

                    code_height = 40
                    prompt_fn_code = st.text_area('Prompt Function', height=code_height, value=template.prompt_fn)
                    output_fn_code = st.text_area('Output Function', height=code_height, value=template.output_fn)

                    reference = st.text_area("Template Reference",
                                             help="Your name and/or paper reference.",
                                             value=template.reference)

                    if st.form_submit_button("Save"):
                        template.jinja = ''
                        template.prompt_fn = prompt_fn_code
                        template.output_fn = output_fn_code
                        template.reference = reference
                        save_data()
            if editor == "Jinja":
                with st.form("edit_template_form"):
                    st.write("Jinja2 Templates.")

                    code_height = 40
                    input_template = st.text_area('Template', height=code_height,
                                                  value=template.jinja_tpl)

                    reference = st.text_area("Template Reference",
                                             help="Your name and/or paper reference.",
                                             value=template.reference)

                    if st.form_submit_button("Save"):
                        template.jinja = input_template
                        template.prompt_fn = ''
                        template.output_fn = ''
                        template.reference = reference
                        save_data()
    #
    # Displays template output on current example if a template is selected
    # (in second column)
    #
    with col2:
        if template_name is not None:
            st.empty()
            st.subheader("Template Output")
            template = dataset_templates[template_name]
            prompt = template.apply(example)
            st.write(prompt[0])
            st.write(prompt[1])
