import tensorflow as tf
from tensorflow.keras import layers, models
import numpy as np
from tensorflow.keras.preprocessing.image import ImageDataGenerator
import cv2

class FaceRecognitionCNN:
    def __init__(self):
        self.model = self._build_model()
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        self.datagen = ImageDataGenerator(
            rotation_range=20,
            width_shift_range=0.2,
            height_shift_range=0.2,
            horizontal_flip=True,
            fill_mode='nearest',
            preprocessing_function=self.preprocess_image
        )
    
    def _build_model(self):
        # Use VGG16 as base model (better for facial features)
        base_model = tf.keras.applications.VGG16(
            input_shape=(224, 224, 3),
            include_top=False,
            weights='imagenet'
        )
        
        # Fine-tune the last few layers
        for layer in base_model.layers[-4:]:
            layer.trainable = True
        
        model = models.Sequential([
            # Input preprocessing
            layers.Input(shape=(224, 224, 3)),
            layers.Rescaling(1./255),
            
            # Data augmentation layers
            layers.RandomRotation(0.2),
            layers.RandomZoom(0.2),
            layers.RandomBrightness(0.2),
            
            # Pre-trained base model
            base_model,
            
            # Classification head
            layers.GlobalAveragePooling2D(),
            layers.Dense(1024, activation='relu'),
            layers.BatchNormalization(),
            layers.Dropout(0.5),
            layers.Dense(512, activation='relu'),
            layers.BatchNormalization(),
            layers.Dropout(0.3),
            layers.Dense(4, activation='softmax')
        ])
        
        # Use a learning rate schedule
        initial_learning_rate = 0.001
        decay_steps = 1000
        decay_rate = 0.9
        learning_rate_schedule = tf.keras.optimizers.schedules.ExponentialDecay(
            initial_learning_rate, decay_steps, decay_rate
        )
        
        model.compile(
            optimizer=tf.keras.optimizers.Adam(learning_rate=learning_rate_schedule),
            loss='sparse_categorical_crossentropy',
            metrics=['accuracy']
        )
        
        return model

    def train_model(self, train_images, train_labels, validation_data=None, epochs=50, batch_size=16, callbacks=None):
        # Add callbacks if not provided
        if callbacks is None:
            callbacks = [
                tf.keras.callbacks.EarlyStopping(
                    monitor='val_accuracy',
                    patience=10,
                    restore_best_weights=True
                ),
                tf.keras.callbacks.ReduceLROnPlateau(
                    monitor='val_loss',
                    factor=0.2,
                    patience=5,
                    min_lr=0.00001
                )
            ]
        
        # Preprocess training data
        preprocessed_train = []
        valid_train_labels = []
        
        for image, label in zip(train_images, train_labels):
            processed = self.preprocess_image(image)
            if processed is not None:
                preprocessed_train.append(processed)
                valid_train_labels.append(label)
        
        preprocessed_train = np.array(preprocessed_train)
        valid_train_labels = np.array(valid_train_labels)
        
        # Preprocess validation data if provided
        if validation_data is not None:
            val_images, val_labels = validation_data
            preprocessed_val = []
            valid_val_labels = []
            
            for image, label in zip(val_images, val_labels):
                processed = self.preprocess_image(image)
                if processed is not None:
                    preprocessed_val.append(processed)
                    valid_val_labels.append(label)
            
            preprocessed_val = np.array(preprocessed_val)
            valid_val_labels = np.array(valid_val_labels)
            validation_data = (preprocessed_val, valid_val_labels)
        
        # Use data augmentation during training
        train_generator = self.datagen.flow(
            preprocessed_train, valid_train_labels,
            batch_size=batch_size
        )
        
        steps_per_epoch = len(preprocessed_train) // batch_size
        
        return self.model.fit(
            train_generator,
            validation_data=validation_data,
            epochs=epochs,
            steps_per_epoch=steps_per_epoch,
            callbacks=callbacks,
            shuffle=True
        )
        
       
    def preprocess_image(self, image):  # Fix indentation here
        # Convert image to uint8 if it's float
        if image.dtype != np.uint8:
            image = (image * 255).astype(np.uint8)
            
        # Detect face and crop
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        else:
            gray = image
            
        faces = self.face_cascade.detectMultiScale(gray, 1.3, 5)
        if len(faces) > 0:
            (x, y, w, h) = faces[0]
            face = image[y:y+h, x:x+w]
            face = cv2.resize(face, (224, 224))
            return face.astype(np.float32) / 255.0  # Ensure float32 type
        return None
    
    

    def predict(self, image):
        processed = self.preprocess_image(image)
        if processed is not None:
            processed = np.expand_dims(processed, axis=0)
            predictions = self.model.predict(processed)
            # Return the predicted class index and confidence
            predicted_class = np.argmax(predictions[0])
            confidence = predictions[0][predicted_class]
            return predicted_class, confidence
        return None, 0.0

    def save_model(self, path):
        # Save the entire model in SavedModel format
        try:
            self.model.save(path, save_format='tf')
        except Exception as e:
            print(f"Error saving model: {e}")
            # Fallback to HDF5 format if TF format fails
            self.model.save(path + '.h5')

    def load_model(self, path):
        try:
            # Try loading SavedModel format
            self.model = models.load_model(path)
        except:
            try:
                # Fallback to HDF5 format
                self.model = models.load_model(path + '.h5')
            except Exception as e:
                print(f"Error loading model: {e}")
                # If both loading attempts fail, create a new model
                self.model = self._build_model()
        
        # Ensure model is compiled
        self.model.compile(
            optimizer=tf.keras.optimizers.Adam(learning_rate=0.001),
            loss='sparse_categorical_crossentropy',
            metrics=['accuracy']
        )