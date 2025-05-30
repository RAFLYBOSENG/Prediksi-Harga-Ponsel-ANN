import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.utils
import json
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from flask import Flask, render_template, request
import pickle
import os
import tensorflow as tf
from tensorflow.keras.models import Sequential, load_model
from tensorflow.keras.layers import Dense, Dropout
from tensorflow.keras.callbacks import EarlyStopping

# Konstanta kurs USD ke IDR
USD_TO_IDR = 15800

class MobileANN:
    def __init__(self):
        self.model = None
        self.encoder = None
        self.scaler = None
        
    def build_model(self, input_dim):
        model = Sequential([
            Dense(64, activation='relu', input_shape=(input_dim,)),
            Dropout(0.2),
            Dense(32, activation='relu'),
            Dropout(0.2),
            Dense(16, activation='relu'),
            Dense(1)  # Output layer untuk prediksi harga
        ])
        
        model.compile(
            optimizer='adam',
            loss='mse',
            metrics=['mae']
        )
        
        return model
    
    def fit(self, X, y):
        # Preprocessing
        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)
        
        # Split data
        X_train, X_val, y_train, y_val = train_test_split(
            X_scaled, y, test_size=0.2, random_state=42
        )
        
        # Build dan train model
        self.model = self.build_model(X.shape[1])
        
        # Early stopping untuk mencegah overfitting
        early_stopping = EarlyStopping(
            monitor='val_loss',
            patience=10,
            restore_best_weights=True
        )
        
        # Training
        history = self.model.fit(
            X_train, y_train,
            validation_data=(X_val, y_val),
            epochs=100,
            batch_size=32,
            callbacks=[early_stopping],
            verbose=1
        )
        
        return history
    
    def predict(self, X):
        X_scaled = self.scaler.transform(X)
        return self.model.predict(X_scaled)
    
    def save(self, path):
        self.model.save(f"{path}_model")
        with open(f"{path}_scaler.pkl", "wb") as f:
            pickle.dump(self.scaler, f)
    
    def load(self, path):
        self.model = load_model(f"{path}_model")
        with open(f"{path}_scaler.pkl", "rb") as f:
            self.scaler = pickle.load(f)

app = Flask(__name__)

# Memuat data ponsel
df = pd.read_csv("dataset_mobile.csv", sep='\t')

# Membuat DataFrame baru untuk fitur
features = ['RAM', 'Front Camera', 'Back Camera', 'Battery Capacity', 'Screen Size']
X = pd.DataFrame()

# Preprocessing data
# Mengubah RAM menjadi angka (misal: '6GB' menjadi 6)
X['ram'] = df['RAM'].str.extract('(\d+)').astype(float)

# Mengubah Front Camera menjadi angka (mengambil angka pertama)
X['front_camera'] = df['Front Camera'].str.extract('(\d+)').astype(float)

# Mengubah Back Camera menjadi angka (mengambil angka pertama)
X['back_camera'] = df['Back Camera'].str.extract('(\d+)').astype(float)

# Mengubah Battery Capacity menjadi angka (menghapus 'mAh')
X['battery'] = df['Battery Capacity'].str.extract('(\d+)').astype(float)

# Mengubah Screen Size menjadi angka (menghapus 'inches')
X['screen'] = df['Screen Size'].str.extract('(\d+\.?\d*)').astype(float)

# Target variable - mengubah harga dari string ke float
def clean_price(price_str):
    # Hapus 'USD ' dan koma, lalu konversi ke float
    return float(price_str.replace('USD ', '').replace(',', ''))

y = df['Launched Price (USA)'].apply(clean_price)

# Encoding untuk brand
brand_encoder = OneHotEncoder(sparse_output=False, handle_unknown='ignore')
brand_encoded = brand_encoder.fit_transform(df[['Company Name']])
brand_encoded_df = pd.DataFrame(brand_encoded, columns=brand_encoder.get_feature_names_out(['Company Name']))

# Scaling numerik features
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)
X_scaled_df = pd.DataFrame(X_scaled, columns=X.columns)

# Menggabungkan semua fitur
X_final = np.hstack((brand_encoded, X_scaled))

# Inisialisasi dan training model ANN
mobile_model = MobileANN()
history = mobile_model.fit(X_final, y)

# Simpan model
mobile_model.save("mobile_ann")

# Menyimpan statistik data
stats = {
    'apple_mean': df[df['Company Name'] == 'Apple']['Launched Price (USA)'].apply(clean_price).mean(),
    'samsung_mean': df[df['Company Name'] == 'Samsung']['Launched Price (USA)'].apply(clean_price).mean() if 'Samsung' in df['Company Name'].values else 0,
    'xiaomi_mean': df[df['Company Name'] == 'Xiaomi']['Launched Price (USA)'].apply(clean_price).mean() if 'Xiaomi' in df['Company Name'].values else 0,
}

# Menyimpan model dan preprocessing objects
with open("model.pkl", "wb") as file:
    pickle.dump((mobile_model, brand_encoder, scaler), file)

# Menyimpan statistik
with open("stats.pkl", "wb") as file:
    pickle.dump(stats, file)

def clean_battery(battery_str):
    # Hapus 'mAh' dan koma, lalu konversi ke float
    return float(battery_str.replace('mAh', '').replace(',', ''))

def get_available_phones():
    phones_by_brand = {}
    for _, row in df.iterrows():
        brand = row['Company Name']
        if brand not in phones_by_brand:
            phones_by_brand[brand] = []
            
        phone_info = {
            'model': row['Model Name'],
            'ram': row['RAM'],
            'front_camera': row['Front Camera'],
            'back_camera': row['Back Camera'],
            'battery': row['Battery Capacity'],
            'screen': row['Screen Size'],
            'price': "{:,.0f}".format(clean_price(row['Launched Price (USA)']) * USD_TO_IDR)
        }
        phones_by_brand[brand].append(phone_info)
    return phones_by_brand

def create_market_price_chart():
    # Membuat DataFrame untuk statistik per merek
    brand_stats = []
    for brand in df['Company Name'].unique():
        brand_data = df[df['Company Name'] == brand]
        prices = brand_data['Launched Price (USA)'].apply(clean_price)
        
        # Menangani outlier dengan metode IQR
        Q1 = prices.quantile(0.25)
        Q3 = prices.quantile(0.75)
        IQR = Q3 - Q1
        lower_bound = Q1 - 1.5 * IQR
        upper_bound = Q3 + 1.5 * IQR
        
        # Filter harga yang valid (tidak outlier)
        valid_prices = prices[(prices >= lower_bound) & (prices <= upper_bound)]
        
        if len(valid_prices) > 0:
            stats = {
                'Brand': brand,
                'Mean': valid_prices.mean() * USD_TO_IDR,
                'Min': valid_prices.min() * USD_TO_IDR,
                'Max': valid_prices.max() * USD_TO_IDR,
                'Count': len(valid_prices)
            }
        else:
            # Jika semua data adalah outlier, gunakan statistik asli
            stats = {
                'Brand': brand,
                'Mean': prices.mean() * USD_TO_IDR,
                'Min': prices.min() * USD_TO_IDR,
                'Max': prices.max() * USD_TO_IDR,
                'Count': len(prices)
            }
        brand_stats.append(stats)
    
    # Konversi ke DataFrame
    brand_stats_df = pd.DataFrame(brand_stats)
    
    # Urutkan berdasarkan harga rata-rata
    brand_stats_df = brand_stats_df.sort_values('Mean', ascending=True)
    
    # Membuat grafik interaktif
    fig = go.Figure()
    
    # Menambahkan bar chart untuk rata-rata harga
    fig.add_trace(go.Bar(
        x=brand_stats_df['Brand'],
        y=brand_stats_df['Mean'],
        name='Rata-rata Harga',
        text=[f'Rp {price:,.0f}' for price in brand_stats_df['Mean']],
        textposition='auto',
        marker_color='#1f77b4'
    ))
    
    # Menambahkan scatter plot untuk harga minimum
    fig.add_trace(go.Scatter(
        x=brand_stats_df['Brand'],
        y=brand_stats_df['Min'],
        mode='lines+markers',
        name='Harga Minimum',
        line=dict(color='#2ca02c', width=2),
        marker=dict(size=8)
    ))
    
    # Menambahkan scatter plot untuk harga maksimum
    fig.add_trace(go.Scatter(
        x=brand_stats_df['Brand'],
        y=brand_stats_df['Max'],
        mode='lines+markers',
        name='Harga Maksimum',
        line=dict(color='#d62728', width=2),
        marker=dict(size=8)
    ))
    
    # Update layout
    fig.update_layout(
        title={
            'text': 'Analisis Harga Ponsel di Pasar (2025)',
            'y':0.95,
            'x':0.5,
            'xanchor': 'center',
            'yanchor': 'top',
            'font': dict(size=20)
        },
        xaxis_title='Merek Ponsel',
        yaxis_title='Harga (IDR)',
        template='plotly_white',
        showlegend=True,
        height=600,
        yaxis=dict(
            tickformat=',',
            tickprefix='Rp ',
            # Batasi range y-axis untuk visualisasi yang lebih baik
            range=[0, brand_stats_df['Max'].median() * 2]
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )
    
    # Menambahkan informasi jumlah model
    for _, row in brand_stats_df.iterrows():
        fig.add_annotation(
            x=row['Brand'],
            y=0,
            text=f'Jumlah Model: {int(row["Count"])}',
            showarrow=False,
            yshift=-30,
            font=dict(size=10)
        )
    
    return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

@app.route("/")
def home():
    phones_by_brand = get_available_phones()
    market_chart = create_market_price_chart()
    return render_template("index.html", 
                         phones_by_brand=phones_by_brand,
                         market_chart=market_chart)

@app.route("/predict", methods=["POST"])
def predict():
    try:
        # Mengambil input dari form
        brand = request.form["brand"]
        ram = float(request.form["ram"])
        front_camera = float(request.form["front_camera"])
        back_camera = float(request.form["back_camera"])
        battery = float(request.form["battery"])
        screen = float(request.form["screen"])
        
        # Preprocessing input
        X_brand = brand_encoder.transform([[brand]])
        X_features = scaler.transform([[ram, front_camera, back_camera, battery, screen]])
        X_combined = np.hstack((X_brand, X_features))
        
        # Prediksi harga dalam USD
        prediksi_harga_usd = mobile_model.predict(X_combined)[0]

        # Dapatkan harga pasar yang sesuai berdasarkan spesifikasi
        similar_phones = []
        for _, row in df[df['Company Name'] == brand].iterrows():
            # Hitung skor kemiripan berdasarkan spesifikasi
            ram_diff = abs(float(row['RAM'].replace('GB', '')) - ram)
            front_cam_diff = abs(float(row['Front Camera'].split('MP')[0]) - front_camera)
            back_cam_diff = abs(float(row['Back Camera'].split('MP')[0]) - back_camera)
            battery_diff = abs(clean_battery(row['Battery Capacity']) - battery) / 1000
            screen_diff = abs(float(row['Screen Size'].replace(' inches', '')) - screen)
            
            # Hitung total perbedaan dengan bobot
            total_diff = (ram_diff * 0.25 + 
                         front_cam_diff * 0.15 + 
                         back_cam_diff * 0.2 + 
                         battery_diff * 0.2 + 
                         screen_diff * 0.2)
            
            if total_diff < 3:  # Ambil ponsel yang cukup mirip
                price = clean_price(row['Launched Price (USA)'])
                similar_phones.append((price, total_diff))

        # Jika ada ponsel yang mirip, gunakan sebagai referensi
        if similar_phones:
            # Urutkan berdasarkan kemiripan (diff terkecil)
            similar_phones.sort(key=lambda x: x[1])
            
            # Ambil 3 ponsel terdekat dan hitung rata-rata tertimbang
            reference_prices = similar_phones[:3]
            total_weight = sum(1 / (diff + 0.1) for _, diff in reference_prices)
            weighted_price = sum((price / (diff + 0.1)) / total_weight 
                                for price, diff in reference_prices)
            
            # Tentukan batas atas (105%) dan batas bawah (98%) dari harga referensi
            upper_limit = weighted_price * 1.05
            lower_limit = weighted_price * 0.98
            
            # Sesuaikan prediksi agar berada dalam range yang diinginkan
            prediksi_harga_usd = max(min(prediksi_harga_usd, upper_limit), lower_limit)
        else:
            # Jika tidak ada ponsel yang mirip, gunakan rata-rata harga brand sebagai patokan
            brand_prices = df[df['Company Name'] == brand]['Launched Price (USA)'].apply(clean_price)
            mean_price = brand_prices.mean()
            
            # Tentukan batas berdasarkan rata-rata harga brand
            upper_limit = mean_price * 1.05
            lower_limit = mean_price * 0.98
            
            # Sesuaikan prediksi
            prediksi_harga_usd = max(min(prediksi_harga_usd, upper_limit), lower_limit)

        # Konversi ke IDR
        prediksi_harga_idr = prediksi_harga_usd * USD_TO_IDR
        
        # Membuat data untuk visualisasi
        brands = df['Company Name'].unique()
        brand_prices = []
        for b in brands:
            prices = df[df['Company Name'] == b]['Launched Price (USA)'].apply(clean_price)
            # Menggunakan median untuk menghindari outlier
            brand_prices.append(prices.median() * USD_TO_IDR)
        
        # Membuat grafik interaktif dengan Plotly
        fig = go.Figure()
        
        # Menambahkan bar chart dengan warna yang sesuai untuk setiap merek
        colors = []
        for b in brands:
            if b == brand:
                colors.append('#FF9999')  # Merah muda untuk merek yang dipilih
            else:
                colors.append('#66B2FF')  # Biru untuk merek lain
        
        # Menambahkan bar chart
        fig.add_trace(go.Bar(
            x=brands,
            y=brand_prices,
            name='Rata-rata Harga per Merek',
            text=[f'Rp {price:,.0f}' for price in brand_prices],
            textposition='auto',
            marker_color=colors
        ))
        
        # Menambahkan scatter plot untuk prediksi
        fig.add_trace(go.Scatter(
            x=[brand],
            y=[prediksi_harga_idr],
            mode='markers',
            name='Prediksi Anda',
            marker=dict(
                color='red',
                size=15,
                line=dict(
                    color='white',
                    width=2
                )
            )
        ))
        
        # Update layout
        fig.update_layout(
            title={
                'text': 'Prediksi Harga Ponsel',
                'y':0.95,
                'x':0.5,
                'xanchor': 'center',
                'yanchor': 'top',
                'font': dict(size=20)
            },
            xaxis_title='Merek Ponsel',
            yaxis_title='Harga (IDR)',
            template='plotly_white',
            showlegend=True,
            height=600,
            yaxis=dict(
                tickformat=',',
                tickprefix='Rp ',
                # Batasi range y-axis
                range=[0, max(brand_prices) * 1.2]
            )
        )
        
        # Konversi grafik ke JSON
        graphJSON = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
        
        # Format statistik dalam IDR
        stats_info = {
            'apple_mean': "{:,.0f}".format(stats['apple_mean'] * USD_TO_IDR),
            'samsung_mean': "{:,.0f}".format(stats['samsung_mean'] * USD_TO_IDR) if stats['samsung_mean'] > 0 else "Tidak tersedia",
            'xiaomi_mean': "{:,.0f}".format(stats['xiaomi_mean'] * USD_TO_IDR) if stats['xiaomi_mean'] > 0 else "Tidak tersedia",
        }
        
        # Mencari ponsel dengan spesifikasi terdekat
        similar_phones = []
        for _, row in df.iterrows():
            if row['Company Name'] == brand:
                # Hitung skor kemiripan berdasarkan spesifikasi
                ram_diff = abs(float(row['RAM'].replace('GB', '')) - ram)
                front_cam_diff = abs(float(row['Front Camera'].split('MP')[0]) - front_camera)
                back_cam_diff = abs(float(row['Back Camera'].split('MP')[0]) - back_camera)
                battery_diff = abs(clean_battery(row['Battery Capacity']) - battery) / 1000  # Normalisasi perbedaan baterai
                screen_diff = abs(float(row['Screen Size'].replace(' inches', '')) - screen)
                
                # Hitung total perbedaan dengan bobot
                total_diff = (ram_diff * 0.2 + 
                            front_cam_diff * 0.15 + 
                            back_cam_diff * 0.15 + 
                            battery_diff * 0.25 + 
                            screen_diff * 0.25)
                
                # Jika total perbedaan kurang dari threshold, tambahkan ke daftar
                if total_diff < 5:  # Threshold yang lebih ketat
                    similar_phones.append({
                        'model': row['Model Name'],
                        'ram': row['RAM'],
                        'front_camera': row['Front Camera'],
                        'back_camera': row['Back Camera'],
                        'battery': row['Battery Capacity'],
                        'screen': row['Screen Size'],
                        'price': "{:,.0f}".format(clean_price(row['Launched Price (USA)']) * USD_TO_IDR),
                        'similarity_score': round(100 - (total_diff * 20), 1)  # Skor kemiripan dalam persen
                    })
        
        # Urutkan ponsel berdasarkan skor kemiripan
        similar_phones.sort(key=lambda x: x['similarity_score'], reverse=True)
        
        # Ambil 5 ponsel teratas
        similar_phones = similar_phones[:5]
        
        # Format prediksi dalam IDR
        harga_format = {
            'nilai': prediksi_harga_idr,
            'format': "{:,.0f}".format(prediksi_harga_idr)
        }
        
        # Informasi spesifikasi yang diinput
        specs_info = {
            'brand': brand,
            'ram': f"{ram}GB",
            'front_camera': f"{front_camera}MP",
            'back_camera': f"{back_camera}MP",
            'battery': f"{battery}mAh",
            'screen': f"{screen} inches"
        }
        
        phones_by_brand = get_available_phones()
        market_chart = create_market_price_chart()
        return render_template("index.html", 
                            prediksi=harga_format, 
                            stats=stats_info, 
                            phones_by_brand=phones_by_brand,
                            specs=specs_info,
                            similar_phones=similar_phones,
                            graphJSON=graphJSON,
                            market_chart=market_chart)
    except Exception as e:
        phones_by_brand = get_available_phones()
        market_chart = create_market_price_chart()
        return render_template("index.html", 
                            error=str(e), 
                            phones_by_brand=phones_by_brand,
                            market_chart=market_chart)

if __name__ == "__main__":
    app.run(debug=True)
