from flask import Flask, render_template, request, redirect, url_for, session
import csv

app = Flask(__name__)
app.secret_key = 'your_secret_key'

def load_questions_from_csv(filename='classified_questions.csv'):
    questions = []
    with open(filename, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if 'Question' not in row:
                print("❌ 'Question' field missing:", row)
                continue
            questions.append({
                'ID': row['ID'],
                'question': row['Question'].strip(),
                'options': [row['OptionA'], row['OptionB'], row['OptionC'], row['OptionD']],
                'answer': row['Answer'],
                'category': row['Category'],
                'type': row.get('Type', 'General')
            })
    return questions

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start_test', methods=['POST'])
def start_test():
    questions = load_questions_from_csv()
    session['questions'] = questions
    session['answers'] = [None] * len(questions)
    return redirect(url_for('show_question', index=0))

@app.route('/question/<int:index>')
def show_question(index):
    questions = session.get('questions')
    if not questions or index >= len(questions):
        return redirect(url_for('index'))
    question = questions[index]
    return render_template('question.html', question=question, q_index=index)

@app.route('/submit_answer', methods=['POST'])
def submit_answer():
    index = int(request.form['q_index'])
    answer = request.form.get('answer')
    answers = session.get('answers')
    if answers is not None and 0 <= index < len(answers):
        answers[index] = answer
        session['answers'] = answers

    next_index = index + 1
    if next_index < len(session['questions']):
        return redirect(url_for('show_question', index=next_index))
    else:
        return redirect(url_for('result'))

@app.route('/result')
def result():
    questions = session.get('questions', [])
    answers = session.get('answers', [])

    question_answer_pairs = []
    score = 0

    for i, q in enumerate(questions):
        user_choice = answers[i]
        options = q['options']

        your_letter = "N/A"
        correct_letter = "N/A"

        if user_choice in options:
            your_letter = "ABCD"[options.index(user_choice)]
        if q['answer'] in options:
            correct_letter = "ABCD"[options.index(q['answer'])]
        if user_choice == q['answer']:
            score += 1

        question_answer_pairs.append({
            "question": q['question'],  # ✅ 用小寫 key
            "options": options,
            "your_answer": user_choice,
            "your_letter": your_letter,
            "correct_answer": q['answer'],
            "correct_letter": correct_letter
        })

    return render_template(
        'result.html',
        question_answer_pairs=question_answer_pairs,
        score=score,
        total=len(questions)
    )

if __name__ == '__main__':
    app.run(debug=True)
