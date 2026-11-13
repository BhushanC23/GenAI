# KubeCoach — Checkpoint 1 Evaluation Guide (Day 5 Review)

> **Student:** Bhushan Kailas Chaturbhuj (Reg. No: 2125PCAM1038)  
> **Project:** KubeCoach (Project ID: SJ-58)  
> **Evaluation Panel:** Checkpoint 1 (Python basics, Git, HTTP/FastAPI, ML concepts, 3-minute project demonstration)

---

## 1. How to Run the KubeCoach FastAPI Application

Follow these exact commands from the `GenAI` repository root:

### Step 1: Open PowerShell and navigate to the project
```powershell
cd "C:\Users\bhushan chaturbhuj\Desktop\KubeCoach\GenAI"
```

### Step 2: Activate the Virtual Environment
```powershell
.\.venv\Scripts\Activate.ps1
```

### Step 3: Install Required Dependencies
```powershell
python -m pip install -r requirements.txt
```

### Step 4: Start the Uvicorn Web Server
```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
Expected terminal output:
```text
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process using WatchFiles
INFO:     Application startup complete.
```

---

## 2. How to Open and Demonstrate Interactive API Documentation (`/docs`)

1. Open your web browser (Chrome / Edge / Firefox).
2. Visit: **`http://127.0.0.1:8000/docs`**
3. You will see the auto-generated **Swagger UI** containing all 5 KubeCoach endpoints:
   - `GET /health` — Click **Try it out** $\rightarrow$ **Execute** $\rightarrow$ Verify HTTP 200 and `{"status": "ok", "records_count": 18}`.
   - `GET /records` — Test `limit=5` $\rightarrow$ Returns first 5 Kubernetes records.
   - `GET /records/{record_id}` — Test `record_id=pod` $\rightarrow$ Returns Pods object details.
   - `GET /search` — Test `q=deployment rollout` $\rightarrow$ Demonstrates smart TF-IDF ranking.
   - `POST /questions` — Send JSON payload `{"question": "What is an Ingress?", "user_name": "Bhushan"}` $\rightarrow$ Returns HTTP 201 Created and persists to `data/questions.json`.
4. Alternative ReDoc specification: **`http://127.0.0.1:8000/redoc`**

---

## 3. Code Walkthrough: Line-by-Line Explanation of `smart_search()`

During the 3-minute Checkpoint 1 review, you will be asked to explain one function from your code. The recommended function is **`smart_search()`** in [`app/smart_search.py`](file:///C:/Users/bhushan%20chaturbhuj/Desktop/KubeCoach/GenAI/app/smart_search.py).

### Quick Summary for the Panel:
> *"In Day 2, our search was a simple keyword substring match, which fails when users ask questions with natural language phrasing. In `app/smart_search.py`, I implemented TF-IDF vectorization and Cosine Similarity from scikit-learn. The function takes the student's question, converts both the question and our 18 Kubernetes records into mathematical vectors, calculates how close their angles are using cosine similarity, and returns the top 3 most relevant records with confidence scores."*

---

### Line-by-Line Breakdown:

#### 1. Function Signature & Inputs
```python
def smart_search(
    query: str,
    records: Optional[List[Dict[str, Any]]] = None,
    top_k: int = 3,
) -> List[Dict[str, Any]]:
```
- **What it receives:**
  - `query`: The user's input string (e.g., *"How do I expose my app over the network?"*).
  - `records`: Optional list of record dictionaries. If not passed, it automatically loads `data/records.json`.
  - `top_k`: Maximum number of top results to return (default is 3).
- **What it returns:** A list of matching record dictionaries with an added `score` float field, sorted descending by relevance.

#### 2. Safe Edge-Case Handling
```python
    cleaned_query = query.strip()
    if not cleaned_query:
        return []
```
- If the user sends an empty string or whitespace, it immediately returns an empty list without wasting CPU cycles.

#### 3. Building the Search Corpus
```python
    dataset = records if records is not None else load_records()
    corpus = [build_corpus_document(rec) for rec in dataset]
```
- For every record, `build_corpus_document()` combines its ID, title, category, definition, kubectl command, and default limits into one rich text string.

#### 4. TF-IDF Vectorization
```python
    vectorizer = TfidfVectorizer(
        stop_words="english",
        token_pattern=r"(?u)\b[a-zA-Z0-9_\-]+\b",
        sublinear_tf=True,
    )
    tfidf_matrix = vectorizer.fit_transform(corpus)
    query_vector = vectorizer.transform([cleaned_query])
```
- **Why this matters:** `TfidfVectorizer` removes meaningless English stopwords (*"is"*, *"a"*, *"the"*). It weights rare technical words higher. `sublinear_tf=True` prevents a word that appears 10 times from dominating ten times more than a word appearing once.
- `fit_transform(corpus)` turns all 18 documents into a numerical matrix.
- `transform([cleaned_query])` projects the user's question into the exact same vector space.

#### 5. Cosine Similarity Calculation
```python
    similarity_scores = cosine_similarity(query_vector, tfidf_matrix).flatten()
```
- Computes the geometric cosine angle between the query vector and all 18 document vectors:
  $$\cos(\theta) = \frac{\mathbf{A} \cdot \mathbf{B}}{\|\mathbf{A}\| \|\mathbf{B}\|}$$
- Returns an array of scores from `0.0` (completely unrelated) to `1.0` (identical).

#### 6. Sorting and Selecting Top Results
```python
    ranked_indices = similarity_scores.argsort()[::-1]
```
- `argsort()[::-1]` sorts the indices from highest similarity score to lowest.
- The loop takes only items with `score > 0.0` and stops once it has gathered `top_k` (3) records.

---

## 4. Viva Cheat Sheet: Expected Questions & Confident Answers

1. **Why do we use Cosine Similarity instead of Euclidean Distance?**
   > *"Euclidean distance measures the physical distance between points, which is distorted by document length—a longer document with more words would look further away. Cosine similarity measures the angle between vectors regardless of document length, focusing purely on topical orientation."*

2. **What happens if a student asks a question about something not in Kubernetes?**
   > *"If no tokens match our vocabulary, or if all cosine similarities are zero, `smart_search()` returns an empty list `[]`, and the API cleanly returns an empty response without crashing."*

3. **How does FastAPI connect to this function?**
   > *"In `app/main.py`, the `GET /search?q={keyword}` endpoint calls `smart_search(q, records=records, top_k=3)`. It keeps API routing completely separated from the search algorithm logic."*

