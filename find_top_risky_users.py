import sqlite3
from app import user_risk_analysis, classify_risk, DATABASE

def find_top_risky_users(top_n=5):   
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()  
    cursor.execute("SELECT id FROM users")
    all_users = cursor.fetchall()
    
    print(f"Found {len(all_users)} total users in database")
    print()
    
    user_scores = []
    for user_row in all_users:
        user_id = user_row[0]
        risk_score = user_risk_analysis(user_id)
        user_scores.append((user_id, risk_score))
    
    user_scores.sort(key=lambda x: x[1], reverse=True)
    top_users = user_scores[:top_n]
    
    top_users_with_labels = [
        (user_id, score, classify_risk(score))
        for user_id, score in top_users
    ]
    
    conn.close()
    return top_users_with_labels, user_scores


def print_results(top_users, all_scores):
    print("Top 5 risky users")
    print()
    print(f"{'Rank':<6} {'User id':<10} {'Risk score':<12} {'Classification':<20}")
    print("-" * 80)
    
    for rank, (user_id, score, label) in enumerate(top_users, start=1):
        print(f"{rank:<6} {user_id:<10} {score:<12.2f} {label:<20}")
    
    print()
    print("Statistics for all users")
    print("=" * 80)
    print()
    
    all_score_values = [score for _, score in all_scores]
    avg_score = sum(all_score_values) / len(all_score_values)
    max_score = max(all_score_values)
    min_score = min(all_score_values)
    
    low_risk = sum(1 for score in all_score_values if score < 1.0)
    medium_risk = sum(1 for score in all_score_values if 1.0 <= score < 3.0)
    high_risk = sum(1 for score in all_score_values if 3.0 <= score < 4.5)
    dangerous = sum(1 for score in all_score_values if score >= 4.5)
    
    total = len(all_scores)
    print(f"total users analyzed: {total}")
    print(f"Average risk score: {avg_score:.2f}")
    print(f"Minimum risk score: {min_score:.2f}")
    print(f"Maximum risk score: {max_score:.2f}")
    print()
    print("risk distribution:")
    print(f"  Low risk (0.0-0.99):{low_risk:4d} users ({low_risk/total*100:.1f}%)")
    print(f"  Medium risk (1.0-2.99):{medium_risk:4d} users ({medium_risk/total*100:.1f}%)")
    print(f"  High risk (3.0-4.49):{high_risk:4d} users ({high_risk/total*100:.1f}%)")
    print(f"  Dangerous! (4.5-5.0):{dangerous:4d} users ({dangerous/total*100:.1f}%)")
    print()


if __name__ == "__main__":
    top_users, all_scores = find_top_risky_users(top_n=5)
    print_results(top_users, all_scores)
    print("=" * 80)
    print("This is the end of the analysis!")