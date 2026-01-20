from time import time
from math import log2, floor
from chess import pgn, Board
import io
import os
import random

def decode(pgn_file_path: str, output_file_path: str) -> None:
    
    try:
        if not os.path.exists(pgn_file_path):
            raise ValueError("Input PGN file does not exist")
            
        # Read PGN file
        with open(pgn_file_path, encoding='utf-8') as pgn_file:
            pgn_content = pgn_file.read()
            
        if not pgn_content.strip():
            raise ValueError("Input PGN file is empty")
            
        # Parse games
        games = []
        pgn_io = io.StringIO(pgn_content)
        while True:
            game = pgn.read_game(pgn_io)
            if game is None:
                break
            games.append(game)
            
        if not games:
            raise ValueError("No valid chess games found in PGN file")
        
        # Check expiry time if present
        current_time = int(time())
        if "ExpiryTime" in games[0].headers:
            expiry_time = int(games[0].headers.get("ExpiryTime"))
            print(f"DEBUG: Current time: {current_time}, Expiry time: {expiry_time}")
            
            if current_time > expiry_time:
                time_diff = current_time - expiry_time
                if time_diff < 60:
                    time_msg = f"{time_diff} seconds"
                elif time_diff < 3600:
                    time_msg = f"{time_diff // 60} minutes"
                else:
                    time_msg = f"{time_diff // 3600} hours"
                
                print(f"DEBUG: File expired {time_msg} ago")
                
                if os.path.exists(output_file_path):
                    os.remove(output_file_path)
                    
                raise ValueError(f"This file has expired {time_msg} ago and can no longer be decrypted")
            else:
                print(f"DEBUG: File valid for {expiry_time - current_time} more seconds")
        
        # Clean up any existing output file
        if os.path.exists(output_file_path):
            os.remove(output_file_path)
        
        all_bits = ""
        
        # Extract bits from all games
        for game_index, game in enumerate(games):
            try:
                base_seed = int(game.headers.get("Seed", "1"))
            except ValueError:
                raise ValueError(f"Invalid seed in game {game_index + 1}")
                
            move_random = random.Random(base_seed)
            board = Board()
            
            for move in game.mainline_moves():
                legal_moves = list(board.legal_moves)
                
                if len(legal_moves) <= 1:
                    board.push(move)
                    continue
                    
                move_random.shuffle(legal_moves)
                
                try:
                    move_index = [m.uci() for m in legal_moves].index(move.uci())
                except ValueError:
                    raise ValueError(f"Invalid move found in game {game_index + 1}: {move.uci()}")
                    
                max_bits = floor(log2(len(legal_moves)))
                
                if max_bits > 0:
                    move_bits = format(move_index, f'0{max_bits}b')
                    all_bits += move_bits
                    
                board.push(move)
        
        print(f"DEBUG: Total extracted bits: {len(all_bits)}")
        
        # Optimized markers - matching encode.py (4 bits each)
        START_MARKER = "1010"
        END_MARKER = "0101"
        
        # Find markers
        start_index = all_bits.find(START_MARKER)
        if start_index == -1:
            raise ValueError("Start marker not found in decoded data")
        
        end_index = all_bits.rfind(END_MARKER)
        data_start = start_index + len(START_MARKER)
        
        if end_index == -1 or end_index <= data_start:
            raise ValueError("End marker not found in decoded data")
        
        # Extract data between markers (includes padding added during encoding)
        data_bits = all_bits[data_start:end_index]
        
        print(f"DEBUG: Found markers - start: {start_index}, end: {end_index}")
        print(f"DEBUG: Data bits length: {len(data_bits)}")
        print(f"DEBUG: Data bits (first 64): {data_bits[:64] if len(data_bits) >= 64 else data_bits}")
        
        # Verify byte alignment
        if len(data_bits) % 8 != 0:
            remainder = len(data_bits) % 8
            print(f"DEBUG: WARNING: Data not byte-aligned, has {remainder} extra bits")
            print(f"DEBUG: This should not happen with the optimized encoder")
            # Truncate the incomplete byte (padding bits)
            data_bits = data_bits[:-(remainder)]
            print(f"DEBUG: Truncated to {len(data_bits)} bits")
        
        if len(data_bits) == 0:
            raise ValueError("No data found between markers")
        
        # Write decoded bytes to file
        with open(output_file_path, 'wb') as f:
            for i in range(0, len(data_bits), 8):
                byte_bits = data_bits[i:i+8]
                if len(byte_bits) == 8:
                    byte_value = int(byte_bits, 2)
                    f.write(bytes([byte_value]))
        
        # Verify output file
        if not os.path.exists(output_file_path):
            raise ValueError("Failed to create output file")
        
        file_size = os.path.getsize(output_file_path)
        if file_size == 0:
            raise ValueError("Decoded output file is empty")
        
        print(f"DEBUG: Successfully decoded {file_size} bytes")
        
    except Exception as e:
        if os.path.exists(output_file_path):
            os.remove(output_file_path)
        raise ValueError(f"Decoding failed: {str(e)}")