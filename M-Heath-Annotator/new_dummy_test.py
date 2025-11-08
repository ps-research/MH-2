from src.utils.validators import validate_response

print('=== Testing ValidationResult fix ===')

# Test urgency
result = validate_response('urgency', 'Analysis here... <<LEVEL_2>>')
print(f'Urgency: is_valid={result.is_valid}, label={result.label}')

# Test therapeutic  
result = validate_response('therapeutic', 'Analysis... <<TA-1>>')
print(f'Therapeutic: is_valid={result.is_valid}, label={result.label}')

# Test redressal
result = validate_response('redressal', 'Analysis... <<[\"stress management\", \"sleep hygiene\"]>>')
print(f'Redressal: is_valid={result.is_valid}, label={result.label}')
