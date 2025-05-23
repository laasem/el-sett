# -*- coding: utf-8 -*-
"""Umm Kulthum (El Sett) model

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1wdeh6w5Tm1CTFD-kJ1xMA4iO6qkpcf_Y

# Install and import packages
"""

# Commented out IPython magic to ensure Python compatibility.
from importlib.util import find_spec
import pip
required_packages = ['torch', 'datasets', 'pandas', 'arabert', 'evaluate', 'rouge_score']
for package in required_packages:
  print(f'Installing package: {package}...')
  pip.main(['install', package])

import torch, evaluate, re, unicodedata
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

from transformers import GPT2LMHeadModel, GPT2TokenizerFast, Trainer, TrainingArguments, TrainerCallback, EvalPrediction
from arabert.preprocess import ArabertPreprocessor
from datasets import Dataset, DatasetDict

# %matplotlib inline
sns.set_style('whitegrid')
plt.rcParams.update({'font.size': 24})

"""# Define model to use"""

MODEL_NAME = 'aubmindlab/aragpt2-medium'

"""# Load existing model unless we want to (re-)train it"""

#@title Do you want to re-train the model even if it already exists?

re_train_model = False #@param

should_fine_tune = re_train_model or False

try:
  model = GPT2LMHeadModel.from_pretrained('./el_sett')
  tokenizer = GPT2Tokenizer.from_pretrained('./el_sett')
  print('Successfully loaded El Sett!')
except:
  should_fine_tune = True
  print('Model does not yet exist - will move on to creating it!')

"""# Create fine-tuned model

## Instantiate model
"""

if should_fine_tune:
  # Load model and tokenizer

  device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

  model = GPT2LMHeadModel.from_pretrained(MODEL_NAME).to(device)

  tokenizer = GPT2TokenizerFast.from_pretrained(MODEL_NAME)
  tokenizer.pad_token = tokenizer.eos_token

"""## Set needed arguments and functions"""

if should_fine_tune:
  training_args = TrainingArguments(
    learning_rate=1e-05, # The learning rate determines how big a step the model should take in the direction indicated by the gradient. A higher learning rate means taking bigger steps, and a lower learning rate means taking smaller steps.
    num_train_epochs=3 #@param #  # Number of times the model will see the entire training data,
                                  # start with a small number of epochs to try out the whole process. Later, increase it: more epochs should lead to better results
    ,
    per_device_train_batch_size=8, # Number of training examples processed at once per device
    per_device_eval_batch_size=8,
    logging_steps=1, # How often to print out logs during training
    output_dir='./training_output', # Where to save the training results
    report_to='none', # prevents automatic logging to wandb which requires sign in
    overwrite_output_dir=True,
    remove_unused_columns=False,
)


  # the following part is needed to keep track of the "loss" during training (see below)
  class LossLoggingCallback(TrainerCallback):
      def __init__(self):
          self.losses = []

      def on_log(self, args, state, control, logs=None, **kwargs):
        print(f'Logging at step {state.global_step}: {logs}')
        # Save the loss
        if 'eval_loss' in logs:
            self.losses.append(logs['eval_loss'])
  # Initialize the callback
  loss_logging_callback = LossLoggingCallback()


# Function to compute ROUGE score for text generation models
def compute_accuracy(p: EvalPrediction):
    preds = p.predictions.argmax(axis=-1)
    model_output = tokenizer.batch_decode(preds, skip_special_tokens=True)
    gold_label = tokenizer.batch_decode(p.label_ids, skip_special_tokens=True)
    rouge = evaluate.load('rouge')
    return rouge.compute(predictions=model_output, references=gold_label)

"""## Load and preprocess data"""

training_data = './training-data.csv'
validation_data = './validation-data.csv'
test_data = './test-data.csv'

df_train = pd.read_csv(training_data, encoding='utf-8')
df_val = pd.read_csv(validation_data, encoding='utf-8')
df_test = pd.read_csv(test_data, encoding='utf-8')

# Convert the pandas DataFrames to Hugging Face Dataset objects
train_dataset = Dataset.from_pandas(df_train)
val_dataset = Dataset.from_pandas(df_val)
test_dataset = Dataset.from_pandas(df_test)

# Create a DatasetDict
dataset = DatasetDict({
    'train': train_dataset,
    'val': val_dataset,
    'test': test_dataset
})

# Preprocess the dataset (tokenize and prepare for training)
def preprocess_batch(batch):
    arabert_prep = ArabertPreprocessor(model_name=MODEL_NAME)

    batch['input_text'] = arabert_prep.preprocess(batch['input_text'])
    batch['target_text'] = arabert_prep.preprocess(batch['target_text'])

    inputs = tokenizer(batch['input_text'], padding='max_length', max_length=60, truncation=True, add_special_tokens=True, return_tensors='pt')
    targets = tokenizer(batch['target_text'], padding='max_length', max_length=60, truncation=True, add_special_tokens=True, return_tensors='pt')

    return {
        'input_ids': inputs['input_ids'],
        'attention_mask': inputs['attention_mask'],
        'labels': targets['input_ids']  # Use target text as labels for language modeling
    }

# Encode the input data
dataset = dataset.map(preprocess_batch, batched=True, remove_columns=['input_text', 'target_text'])

# Transform to pytorch tensors and only output the required columns
dataset.set_format(type='torch', columns=['input_ids', 'attention_mask', 'labels'])

"""## Fine-tune model"""

if should_fine_tune:
  trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=dataset["train"],
    eval_dataset=dataset["val"],
    compute_metrics=compute_accuracy,
    callbacks=[loss_logging_callback]
)

  trainer.train()

plt.bar(range(len(loss_logging_callback.losses)), loss_logging_callback.losses)
plt.xlabel('Steps')
plt.ylabel('Loss')
plt.title('Loss per Logging Step')
plt.show()

"""## Save fine-tuned model and tokenizer"""

if should_fine_tune:
  # Save the model and tokenizer

  model.save_pretrained('./el_sett')
  tokenizer.save_pretrained('./el_sett')

"""# Quantitative evaluation: Model's ROUGE score

## Evaluate on validation data
"""

!pip install rouge_score

trainer.evaluate()

"""## Evaluate on test data"""

trainer.evaluate(eval_dataset=dataset['test'])

"""## Compare to non-finetuned Arabic GPT2 model"""

non_finetuned_model = GPT2LMHeadModel.from_pretrained(MODEL_NAME).to(device)

# Not actually training/fine-tuning; just using the class to evaluate!
trainer = Trainer(
    model=non_finetuned_model,
    args=training_args,
    train_dataset=dataset["train"],
    eval_dataset=dataset["val"],
    compute_metrics=compute_accuracy
)
trainer.evaluate()

"""# Qualitative evaluation: Manually inspect examples"""

# @title Function to call model and make it generate text
def generate_text(input_text, target_text):
  input_ids = tokenizer.encode(input_text, return_tensors='pt').to(device)

  output = model.generate(
      input_ids,                        # Input tokens
      min_length=30,                    # Minimum length to ensure enough content
      max_length=500,                   # Max length around 30 words (100 tokens for flexibility)
      do_sample=True,                   # Enable sampling to allow for diverse outputs
      temperature=0.6,                   # Lower temperature for more focused generation
      top_p=0.5,                        # Slightly lower top_p for focused diversity
      top_k=30,                          # Lower top_k to reduce random choices
      no_repeat_ngram_size=3,            # Avoid repeating trigrams
      repetition_penalty=2.0,            # Avoid excessive repetition
      eos_token_id=tokenizer.eos_token_id,  # Ensure EOS is handled properly
      pad_token_id=tokenizer.pad_token_id  # Ensure proper padding
  )

  # Decode the generated tokens back into text
  generated_ids = output[:, input_ids.shape[-1]:]  # Skip input tokens
  generated_text = tokenizer.decode(generated_ids[0], skip_special_tokens=True)

  print('Rest of song generated by model:')
  print(generated_text)

  print()

  print('Actual rest of song:')
  print(target_text)

input_text = "ذكريات (قصة حبى) عبرت افق خيالي بارقا يلمع في جنح الليالي نبهت قلبي من غفوته وجلت لي ذكرى ايامي الخوالي كيف انساها وقلبي لم يزل يذكر جمبي انها قصة حبي ذكريات داعبت فكري وظني لست ادري ايها اقرب مني هي في سمعي على طول المدى نغم ينساب في لحن اغن بين شدو و حنيني وبكاء وانيني كيف انساها وسمعي لم يزل لم يزل يذكر سمعي وانا ابكي مع اللحن الحزين كان فجرا باسما في مقلتي يوم اشرقت من الغيب عليه انست روحي الى طلعته وتلت ظهر الهوى فسقيناهوا ودادا ورعيناهوا وفاءا ثم همنا فيه شوقا وقطعنا لقاه كيف لا يشغل فكري طلعت كالبدر يسري رقة كالماء يجري فتنة في الحب تغري تترك الخالي شهيا كيف انسى ذكرياتي وهي في قلبي عليل كيف انسى ذكرياتي وهي في سمعي رنيين كيف انسى ذكرياتي وهي احلام حياتي انها صورة ايامي على مراتي ساقي عشت فيها بيقيني وهي قرب ووقار ثم عاشت في ظنوني وهي وهم وخيال ثم تبقالي على بر السنين وهي لي ماضي من العمر" # @param {type:"string"}

target_text = "واتي كيف انساها وقلبي لم يزل يذكر جمبي انها قصة حبي" # @param {type:"string"}

generate_text(input_text, target_text)