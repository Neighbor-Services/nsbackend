import uuid

def _wrap_appointments(data, current_user_id):
    wrapped = []
    for item in data:
        seeker_profile = item.get('seeker_profile')
        provider_profile = item.get('provider_profile')
        is_seeker = str(item.get('seeker')) == str(current_user_id)
        if is_seeker:
            user_profile = provider_profile
            role = 'seeker'
        else:
            user_profile = seeker_profile
            role = 'provider'
        wrapped.append({
            'appointment': item,
            'user': user_profile,
            'role': role
        })
    return wrapped

user1_id = uuid.uuid4()
user2_id = uuid.uuid4()

mock_data = [
    {
        'id': 'appt1',
        'seeker': str(user1_id),
        'provider': str(user2_id),
        'seeker_profile': {'name': 'User 1'},
        'provider_profile': {'name': 'User 2'}
    },
    {
        'id': 'appt2',
        'seeker': str(user2_id),
        'provider': str(user1_id),
        'seeker_profile': {'name': 'User 2'},
        'provider_profile': {'name': 'User 1'}
    }
]

print('As User 1 (Seeker in appt1, Provider in appt2):')
wrapped_as_user1 = _wrap_appointments(mock_data, user1_id)
for w in wrapped_as_user1:
    print(f"Appt: {w['appointment']['id']}, Role: {w['role']}, Other User: {w['user']['name']}")

print('\nAs User 2 (Provider in appt1, Seeker in appt2):')
wrapped_as_user2 = _wrap_appointments(mock_data, user2_id)
for w in wrapped_as_user2:
    print(f"Appt: {w['appointment']['id']}, Role: {w['role']}, Other User: {w['user']['name']}")
